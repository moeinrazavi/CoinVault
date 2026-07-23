#!/usr/bin/env python3
"""CoinVault - MAME arcade library with drag-and-drop game import."""

from __future__ import annotations

import sys
import threading
import traceback
from pathlib import Path

import AppKit
import Foundation
import objc

from emulator.controller import ensure_controller_ready
from emulator.controller_editor import show_controller_editor
from emulator.game_library import GameEntry, GameLibrary
from emulator.launcher import run_game_entry
from emulator.library_bootstrap import bootstrap_library
from emulator.paths import APP_NAME, library_root

NSFilenamesPboardType = AppKit.NSFilenamesPboardType
NSPasteboardTypeFileURL = AppKit.NSPasteboardTypeFileURL


def _log(message: str) -> None:
    print(f"[{APP_NAME}] {message}", flush=True)


class GameTileView(AppKit.NSView):
    entry = objc.ivar("entry")
    on_activate = objc.ivar("on_activate")
    on_select = objc.ivar("on_select")
    selected = objc.ivar("selected")

    def initWithFrame_entry_callback_select_(self, frame, entry, callback, select):
        self = objc.super(GameTileView, self).initWithFrame_(frame)
        if self is None:
            return None

        self.entry = entry
        self.on_activate = callback
        self.on_select = select
        self.selected = False
        self.setWantsLayer_(True)
        self._apply_style()

        image_view = AppKit.NSImageView.alloc().initWithFrame_(
            Foundation.NSMakeRect(12, 36, 136, 136)
        )
        image_view.setImageScaling_(AppKit.NSImageScaleProportionallyUpOrDown)
        image = AppKit.NSImage.alloc().initWithContentsOfFile_(
            str(entry.icon_path)
        )
        if image is not None:
            image_view.setImage_(image)
        else:
            image_view.setImage_(AppKit.NSImage.imageNamed_("NSApplicationIcon"))
        self.addSubview_(image_view)

        title = AppKit.NSTextField.labelWithString_(entry.title)
        title.setFrame_(Foundation.NSMakeRect(8, 14, 144, 18))
        title.setFont_(AppKit.NSFont.boldSystemFontOfSize_(11))
        title.setAlignment_(AppKit.NSTextAlignmentCenter)
        title.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        self.addSubview_(title)

        subtitle = AppKit.NSTextField.labelWithString_(
            entry.year or entry.manufacturer or entry.id
        )
        subtitle.setFrame_(Foundation.NSMakeRect(8, 2, 144, 14))
        subtitle.setFont_(AppKit.NSFont.systemFontOfSize_(10))
        subtitle.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        subtitle.setAlignment_(AppKit.NSTextAlignmentCenter)
        self.addSubview_(subtitle)
        return self

    @objc.python_method
    def _apply_style(self) -> None:
        self.layer().setCornerRadius_(16)
        if self.selected:
            self.layer().setBackgroundColor_(
                AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.18, 0.32, 0.58, 1.0
                ).CGColor()
            )
            self.layer().setBorderWidth_(2.0)
            self.layer().setBorderColor_(
                AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.45, 0.72, 1.0, 1.0
                ).CGColor()
            )
        else:
            self.layer().setBorderWidth_(0.0)
            self.layer().setBackgroundColor_(
                AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                    0.14, 0.16, 0.2, 1.0
                ).CGColor()
            )

    def setSelected_(self, selected) -> None:
        self.selected = bool(selected)
        self._apply_style()

    def mouseDown_(self, event):
        if self.on_select is not None:
            self.on_select(self.entry)
        if event.clickCount() >= 2 and self.on_activate is not None:
            self.on_activate(self.entry)


class DropView(AppKit.NSView):
    callback = objc.ivar("callback")

    def initWithFrame_callback_(self, frame, callback):
        self = objc.super(DropView, self).initWithFrame_(frame)
        if self is None:
            return None

        self.callback = callback
        self.registerForDraggedTypes_([NSFilenamesPboardType, NSPasteboardTypeFileURL])
        self.setWantsLayer_(True)
        self.layer().setCornerRadius_(18)
        self._apply_idle_style()

        label = AppKit.NSTextField.labelWithString_("Drop a game ROM folder here")
        label.setFrame_(Foundation.NSMakeRect(20, 58, frame.size.width - 40, 28))
        label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(18))
        label.setAlignment_(AppKit.NSTextAlignmentCenter)
        self.addSubview_(label)

        hint = AppKit.NSTextField.labelWithString_(
            "Drag ROM folders here. Use Controller Setup in the toolbar to map keys."
        )
        hint.setFrame_(Foundation.NSMakeRect(20, 28, frame.size.width - 40, 20))
        hint.setFont_(AppKit.NSFont.systemFontOfSize_(12))
        hint.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        hint.setAlignment_(AppKit.NSTextAlignmentCenter)
        self.addSubview_(hint)
        return self

    @objc.python_method
    def _apply_idle_style(self) -> None:
        self.layer().setBackgroundColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.11, 0.13, 0.17, 1.0
            ).CGColor()
        )
        self.layer().setBorderWidth_(1.5)
        self.layer().setBorderColor_(
            AppKit.NSColor.colorWithCalibratedWhite_alpha_(0.35, 1.0).CGColor()
        )

    @objc.python_method
    def _apply_active_style(self) -> None:
        self.layer().setBackgroundColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.16, 0.28, 0.48, 1.0
            ).CGColor()
        )
        self.layer().setBorderColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.45, 0.72, 1.0, 1.0
            ).CGColor()
        )

    def draggingEntered_(self, sender):
        self._apply_active_style()
        return AppKit.NSDragOperationCopy

    def draggingExited_(self, sender):
        self._apply_idle_style()

    def performDragOperation_(self, sender):
        self._apply_idle_style()
        paths = self._paths_from_pasteboard(sender.draggingPasteboard())
        folders = [Path(path) for path in paths if Path(path).is_dir()]
        if folders and self.callback is not None:
            self.callback(folders[0])
            return True
        return False

    @objc.python_method
    def _paths_from_pasteboard(self, pasteboard) -> list[str]:
        urls = pasteboard.readObjectsForClasses_options_(
            [Foundation.NSURL],
            {},
        )
        if urls:
            return [
                url.path()
                for url in urls
                if url is not None and url.isFileURL()
            ]

        return pasteboard.propertyListForType_(NSFilenamesPboardType) or []


class AppDelegate(AppKit.NSObject):
    window = objc.ivar("window")
    status_label = objc.ivar("status_label")
    grid_view = objc.ivar("grid_view")
    library = objc.ivar("library")
    launch_thread = objc.ivar("launch_thread")
    selected_entry = objc.ivar("selected_entry")
    tile_views = objc.ivar("tile_views")
    controller_editor = objc.ivar("controller_editor")

    def applicationDidFinishLaunching_(self, notification):
        bootstrap_library()
        ensure_controller_ready()
        self.library = GameLibrary()
        self.launch_thread = None
        self.selected_entry = None
        self.tile_views = []
        self.controller_editor = None

        self._build_menu_bar()

        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            Foundation.NSMakeRect(0, 0, 920, 680),
            AppKit.NSWindowStyleMaskTitled
            | AppKit.NSWindowStyleMaskClosable
            | AppKit.NSWindowStyleMaskMiniaturizable
            | AppKit.NSWindowStyleMaskResizable,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_(APP_NAME)
        self.window.center()
        self.window.setMinSize_(Foundation.NSMakeSize(720, 560))

        content = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, 920, 680)
        )
        self.window.setContentView_(content)

        toolbar = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 600, 920, 80)
        )
        toolbar.setWantsLayer_(True)
        toolbar.layer().setBackgroundColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.10, 0.12, 0.16, 1.0
            ).CGColor()
        )
        content.addSubview_(toolbar)

        title = AppKit.NSTextField.labelWithString_("Your Arcade Library")
        title.setFrame_(Foundation.NSMakeRect(24, 28, 400, 28))
        title.setFont_(AppKit.NSFont.boldSystemFontOfSize_(24))
        title.setTextColor_(AppKit.NSColor.labelColor())
        toolbar.addSubview_(title)

        setup_button = AppKit.NSButton.alloc().initWithFrame_(
            Foundation.NSMakeRect(620, 22, 160, 32)
        )
        setup_button.setTitle_("Controller Setup")
        setup_button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        setup_button.setTarget_(self)
        setup_button.setAction_("openControls:")
        toolbar.addSubview_(setup_button)

        remove_button = AppKit.NSButton.alloc().initWithFrame_(
            Foundation.NSMakeRect(792, 22, 104, 32)
        )
        remove_button.setTitle_("Remove Game")
        remove_button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        remove_button.setTarget_(self)
        remove_button.setAction_("removeSelected:")
        toolbar.addSubview_(remove_button)

        self.status_label = AppKit.NSTextField.labelWithString_("Ready")
        self.status_label.setFrame_(Foundation.NSMakeRect(24, 24, 760, 20))
        self.status_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        content.addSubview_(self.status_label)

        drop_view = DropView.alloc().initWithFrame_callback_(
            Foundation.NSMakeRect(24, 470, 872, 108),
            self.import_folder_,
        )
        content.addSubview_(drop_view)

        scroll = AppKit.NSScrollView.alloc().initWithFrame_(
            Foundation.NSMakeRect(24, 56, 872, 400)
        )
        scroll.setHasVerticalScroller_(True)
        scroll.setDrawsBackground_(False)
        scroll.setBorderType_(AppKit.NSNoBorder)

        self.grid_view = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, 840, 400)
        )
        scroll.setDocumentView_(self.grid_view)
        content.addSubview_(scroll)

        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        self.reload_library_()
        self.updateStatusMessage_(
            "Double-click a game to play. Use Controller Setup to map keyboard keys."
        )

    @objc.python_method
    def _build_menu_bar(self) -> None:
        main_menu = AppKit.NSMenu.alloc().init()

        app_menu_item = AppKit.NSMenuItem.alloc().init()
        main_menu.addItem_(app_menu_item)
        app_menu = AppKit.NSMenu.alloc().init()
        app_menu_item.setSubmenu_(app_menu)

        about_item = app_menu.addItemWithTitle_action_keyEquivalent_(
            f"About {APP_NAME}",
            "orderFrontStandardAboutPanel:",
            "",
        )
        about_item.setTarget_(AppKit.NSApp)
        app_menu.addItem_(AppKit.NSMenuItem.separatorItem())
        controller_app_item = app_menu.addItemWithTitle_action_keyEquivalent_(
            "Controller Setup...",
            "openControls:",
            ",",
        )
        controller_app_item.setTarget_(self)
        app_menu.addItem_(AppKit.NSMenuItem.separatorItem())
        quit_item = app_menu.addItemWithTitle_action_keyEquivalent_(
            f"Quit {APP_NAME}",
            "terminate:",
            "q",
        )
        quit_item.setTarget_(AppKit.NSApp)

        setup_menu_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Setup",
            None,
            "",
        )
        main_menu.addItem_(setup_menu_item)
        setup_menu = AppKit.NSMenu.alloc().init()
        setup_menu_item.setSubmenu_(setup_menu)
        controller_setup_item = setup_menu.addItemWithTitle_action_keyEquivalent_(
            "Controller Setup...",
            "openControls:",
            ",",
        )
        controller_setup_item.setTarget_(self)

        AppKit.NSApp.setMainMenu_(main_menu)

    @objc.python_method
    def updateStatusMessage_(self, message) -> None:
        self.status_label.setStringValue_(message)

    @objc.python_method
    def reload_library_(self) -> None:
        for subview in list(self.grid_view.subviews()):
            subview.removeFromSuperview()

        games = self.library.list_games()
        self.tile_views = []
        columns = 5
        tile_width = 160
        tile_height = 190
        padding = 16

        rows = max(1, (len(games) + columns - 1) // columns)
        height = rows * (tile_height + padding) + padding
        self.grid_view.setFrameSize_(Foundation.NSMakeSize(840, max(height, 400)))

        if not games:
            empty = AppKit.NSTextField.labelWithString_(
                "No games yet. Drag a ROM folder into the drop zone above."
            )
            empty.setFrame_(Foundation.NSMakeRect(180, 180, 480, 24))
            empty.setAlignment_(AppKit.NSTextAlignmentCenter)
            empty.setTextColor_(AppKit.NSColor.secondaryLabelColor())
            self.grid_view.addSubview_(empty)
            return

        for index, entry in enumerate(games):
            row = index // columns
            col = index % columns
            x = padding + col * (tile_width + padding)
            y = height - padding - (row + 1) * (tile_height + padding)
            tile = GameTileView.alloc().initWithFrame_entry_callback_select_(
                Foundation.NSMakeRect(x, y, tile_width, tile_height),
                entry,
                self.launch_game_,
                self.select_game_,
            )
            if self.selected_entry and self.selected_entry.id == entry.id:
                tile.setSelected_(True)
            self.tile_views.append(tile)
            self.grid_view.addSubview_(tile)

    @objc.python_method
    def select_game_(self, entry: GameEntry) -> None:
        self.selected_entry = entry
        for tile in self.tile_views:
            tile.setSelected_(tile.entry.id == entry.id)
        self.updateStatusMessage_(f"Selected {entry.title}. Double-click to play.")

    @objc.python_method
    def _show_error(self, title: str, message: str) -> None:
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(title)
        alert.setInformativeText_(message)
        alert.runModal()

    @objc.python_method
    def import_folder_(self, folder: Path) -> None:
        self.updateStatusMessage_(f"Importing {folder.name}...")
        threading.Thread(
            target=self._import_worker,
            args=(folder,),
            daemon=True,
        ).start()

    @objc.python_method
    def _import_worker(self, folder: Path) -> None:
        try:
            def progress(message: str) -> None:
                AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
                    lambda: self.updateStatusMessage_(message)
                )

            entry = self.library.add_game_from_folder(folder, progress=progress)
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: self._import_finished(entry, None)
            )
        except Exception as exc:
            AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: self._import_finished(None, exc)
            )

    @objc.python_method
    def _import_finished(self, entry: GameEntry | None, error: Exception | None) -> None:
        if error is not None:
            self._show_error("Import Failed", str(error))
            self.updateStatusMessage_("Import failed")
            _log(traceback.format_exc())
            return

        self.reload_library_()
        self.updateStatusMessage_(f"Added {entry.title}")

    @objc.python_method
    def launch_game_(self, entry: GameEntry) -> None:
        if self.launch_thread and self.launch_thread.is_alive():
            self.updateStatusMessage_("A game is already running")
            return

        self.updateStatusMessage_(f"Launching {entry.title}...")
        self.launch_thread = threading.Thread(
            target=self._launch_worker,
            args=(entry,),
            daemon=True,
        )
        self.launch_thread.start()

    @objc.python_method
    def _launch_worker(self, entry: GameEntry) -> None:
        try:
            exit_code = run_game_entry(entry)
            message = f"{entry.title} exited ({exit_code})"
        except Exception as exc:
            message = f"Launch failed: {exc}"
            _log(traceback.format_exc())

        AppKit.NSOperationQueue.mainQueue().addOperationWithBlock_(
            lambda: self.updateStatusMessage_(message)
        )

    def openControls_(self, sender) -> None:
        if self.controller_editor is None:
            self.controller_editor = show_controller_editor()
        else:
            self.controller_editor.show()

    def removeSelected_(self, sender) -> None:
        if self.selected_entry is None:
            self._show_error("Remove Game", "Click a game tile first, then press Remove.")
            return

        entry = self.selected_entry
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_(f"Remove {entry.title}?")
        alert.setInformativeText_(
            "This deletes the imported ROM files and save data for this game."
        )
        alert.addButtonWithTitle_("Remove")
        alert.addButtonWithTitle_("Cancel")
        if alert.runModal() == AppKit.NSAlertFirstButtonReturn:
            self.library.remove_game(entry.id)
            self.selected_entry = None
            self.reload_library_()
            self.updateStatusMessage_(f"Removed {entry.title}")

    def applicationShouldTerminateAfterLastWindowClosed_(self, sender):
        return True


def main() -> int:
    app = AppKit.NSApplication.sharedApplication()
    AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)

    delegate = AppDelegate.alloc().init()
    AppKit.NSApp.setDelegate_(delegate)
    AppKit.NSApp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
