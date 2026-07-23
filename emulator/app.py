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
from PyObjCTools import AppHelper

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
    image_view = objc.ivar("image_view")
    title_label = objc.ivar("title_label")
    subtitle_label = objc.ivar("subtitle_label")

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

        tile_width = frame.size.width
        image_size = max(96, tile_width - 24)
        image_y = 34

        self.image_view = AppKit.NSImageView.alloc().initWithFrame_(
            Foundation.NSMakeRect(
                (tile_width - image_size) / 2,
                image_y,
                image_size,
                image_size,
            )
        )
        self.image_view.setImageScaling_(AppKit.NSImageScaleProportionallyUpOrDown)
        image = AppKit.NSImage.alloc().initWithContentsOfFile_(
            str(entry.icon_path)
        )
        if image is not None:
            self.image_view.setImage_(image)
        else:
            self.image_view.setImage_(AppKit.NSImage.imageNamed_("NSApplicationIcon"))
        self.addSubview_(self.image_view)

        self.title_label = AppKit.NSTextField.labelWithString_(entry.title)
        self.title_label.setFrame_(
            Foundation.NSMakeRect(8, 14, tile_width - 16, 18)
        )
        self.title_label.setFont_(AppKit.NSFont.boldSystemFontOfSize_(11))
        self.title_label.setAlignment_(AppKit.NSTextAlignmentCenter)
        self.title_label.setLineBreakMode_(AppKit.NSLineBreakByTruncatingTail)
        self.addSubview_(self.title_label)

        self.subtitle_label = AppKit.NSTextField.labelWithString_(
            entry.year or entry.manufacturer or entry.id
        )
        self.subtitle_label.setFrame_(
            Foundation.NSMakeRect(8, 2, tile_width - 16, 14)
        )
        self.subtitle_label.setFont_(AppKit.NSFont.systemFontOfSize_(10))
        self.subtitle_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        self.subtitle_label.setAlignment_(AppKit.NSTextAlignmentCenter)
        self.addSubview_(self.subtitle_label)
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
    content_view = objc.ivar("content_view")
    toolbar = objc.ivar("toolbar")
    drop_view = objc.ivar("drop_view")
    library_scroll = objc.ivar("library_scroll")
    status_label = objc.ivar("status_label")
    grid_view = objc.ivar("grid_view")
    empty_label = objc.ivar("empty_label")
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
        self.empty_label = None

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
        self.window.setDelegate_(self)

        self.content_view = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, 920, 680)
        )
        self.window.setContentView_(self.content_view)

        self.toolbar = AppKit.NSView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, 920, 80))
        self.toolbar.setWantsLayer_(True)
        self.toolbar.layer().setBackgroundColor_(
            AppKit.NSColor.colorWithCalibratedRed_green_blue_alpha_(
                0.10, 0.12, 0.16, 1.0
            ).CGColor()
        )
        self.content_view.addSubview_(self.toolbar)

        title = AppKit.NSTextField.labelWithString_("Your Arcade Library")
        title.setFrame_(Foundation.NSMakeRect(24, 28, 400, 28))
        title.setFont_(AppKit.NSFont.boldSystemFontOfSize_(24))
        title.setTextColor_(AppKit.NSColor.labelColor())
        self.toolbar.addSubview_(title)

        setup_button = AppKit.NSButton.alloc().initWithFrame_(
            Foundation.NSMakeRect(620, 22, 160, 32)
        )
        setup_button.setTitle_("Controller Setup")
        setup_button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        setup_button.setTarget_(self)
        setup_button.setAction_("openControls:")
        self.toolbar.addSubview_(setup_button)

        remove_button = AppKit.NSButton.alloc().initWithFrame_(
            Foundation.NSMakeRect(792, 22, 104, 32)
        )
        remove_button.setTitle_("Remove Game")
        remove_button.setBezelStyle_(AppKit.NSBezelStyleRounded)
        remove_button.setTarget_(self)
        remove_button.setAction_("removeSelected:")
        self.toolbar.addSubview_(remove_button)

        self.status_label = AppKit.NSTextField.labelWithString_("Ready")
        self.status_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
        self.content_view.addSubview_(self.status_label)

        self.drop_view = DropView.alloc().initWithFrame_callback_(
            Foundation.NSMakeRect(0, 0, 872, 108),
            self.import_folder_,
        )
        self.content_view.addSubview_(self.drop_view)

        self.library_scroll = AppKit.NSScrollView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, 872, 400)
        )
        self.library_scroll.setHasVerticalScroller_(True)
        self.library_scroll.setHasHorizontalScroller_(False)
        self.library_scroll.setAutohidesScrollers_(True)
        self.library_scroll.setDrawsBackground_(False)
        self.library_scroll.setBorderType_(AppKit.NSNoBorder)

        self.grid_view = AppKit.NSView.alloc().initWithFrame_(
            Foundation.NSMakeRect(0, 0, 840, 400)
        )
        self.library_scroll.setDocumentView_(self.grid_view)
        self.content_view.addSubview_(self.library_scroll)

        self._layout_ui_()
        self.window.makeKeyAndOrderFront_(None)
        AppKit.NSApp.activateIgnoringOtherApps_(True)
        self.reload_library_()
        self.updateStatusMessage_(
            "Double-click a game to play. Use Controller Setup to map keyboard keys."
        )
        if self.library.artwork_needs_refresh():
            self.updateStatusMessage_("Updating library artwork...")
            threading.Thread(
                target=self._refresh_artwork_worker,
                daemon=True,
            ).start()

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
    def _layout_ui_(self) -> None:
        bounds = self.content_view.bounds()
        width = bounds.size.width
        height = bounds.size.height
        margin = 24
        toolbar_height = 80
        drop_height = 108
        status_height = 22
        section_gap = 12

        self.toolbar.setFrame_(
            Foundation.NSMakeRect(0, height - toolbar_height, width, toolbar_height)
        )

        toolbar_buttons = self.toolbar.subviews()
        if len(toolbar_buttons) >= 3:
            setup_button = toolbar_buttons[1]
            remove_button = toolbar_buttons[2]
            remove_button.setFrame_(
                Foundation.NSMakeRect(max(width - margin - 104, 680), 22, 104, 32)
            )
            setup_button.setFrame_(
                Foundation.NSMakeRect(max(width - margin - 272, 520), 22, 160, 32)
            )

        drop_y = height - toolbar_height - section_gap - drop_height
        self.drop_view.setFrame_(
            Foundation.NSMakeRect(margin, drop_y, width - (margin * 2), drop_height)
        )

        for subview in self.drop_view.subviews():
            if isinstance(subview, AppKit.NSTextField):
                frame = subview.frame()
                subview.setFrame_(
                    Foundation.NSMakeRect(
                        20,
                        frame.origin.y,
                        self.drop_view.frame().size.width - 40,
                        frame.size.height,
                    )
                )

        self.status_label.setFrame_(
            Foundation.NSMakeRect(margin, 16, width - (margin * 2), status_height)
        )

        scroll_y = 16 + status_height + section_gap
        scroll_height = max(
            160,
            drop_y - scroll_y - section_gap,
        )
        self.library_scroll.setFrame_(
            Foundation.NSMakeRect(
                margin,
                scroll_y,
                width - (margin * 2),
                scroll_height,
            )
        )

    @objc.python_method
    def _grid_metrics(self) -> tuple[int, int, int, int, float]:
        viewport_width = self.library_scroll.contentSize().width
        if viewport_width < 120:
            viewport_width = self.library_scroll.frame().size.width
        padding = 16
        min_tile = 148
        max_tile = 188
        columns = max(1, int((viewport_width - padding) // (min_tile + padding)))
        tile_width = int((viewport_width - padding * (columns + 1)) / columns)
        tile_width = max(min_tile, min(tile_width, max_tile))
        tile_height = int(tile_width * 1.18)
        return columns, tile_width, tile_height, padding, viewport_width

    def windowDidResize_(self, notification) -> None:
        self._layout_ui_()
        self._layout_library_grid_()

    @objc.python_method
    def updateStatusMessage_(self, message) -> None:
        self.status_label.setStringValue_(message)

    @objc.python_method
    def reload_library_(self) -> None:
        self._layout_ui_()
        self._layout_library_grid_()

    @objc.python_method
    def _layout_library_grid_(self) -> None:
        for subview in list(self.grid_view.subviews()):
            subview.removeFromSuperview()
        if self.empty_label is not None:
            self.empty_label.removeFromSuperview()
            self.empty_label = None

        games = self.library.list_games()
        self.tile_views = []
        columns, tile_width, tile_height, padding, viewport_width = self._grid_metrics()
        viewport_height = self.library_scroll.contentSize().height
        if viewport_height < 120:
            viewport_height = self.library_scroll.frame().size.height

        if not games:
            self.empty_label = AppKit.NSTextField.labelWithString_(
                "No games yet. Drag a ROM folder into the drop zone above."
            )
            self.empty_label.setAlignment_(AppKit.NSTextAlignmentCenter)
            self.empty_label.setTextColor_(AppKit.NSColor.secondaryLabelColor())
            self.empty_label.setFrame_(
                Foundation.NSMakeRect(
                    0,
                    max(0, (viewport_height - 24) / 2),
                    viewport_width,
                    24,
                )
            )
            self.grid_view.addSubview_(self.empty_label)
            self.grid_view.setFrameSize_(
                Foundation.NSMakeSize(viewport_width, max(viewport_height, 220))
            )
            return

        rows = max(1, (len(games) + columns - 1) // columns)
        content_height = rows * (tile_height + padding) + padding
        content_height = max(content_height, viewport_height)
        self.grid_view.setFrameSize_(
            Foundation.NSMakeSize(viewport_width, content_height)
        )

        for index, entry in enumerate(games):
            row = index // columns
            col = index % columns
            x = padding + col * (tile_width + padding)
            y = content_height - padding - (row + 1) * (tile_height + padding)
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
    def _refresh_artwork_worker(self) -> None:
        try:
            def progress(message: str) -> None:
                AppHelper.callAfter(self.updateStatusMessage_, message)

            updated = self.library.refresh_all_icons(progress=progress)
            AppHelper.callAfter(
                self._artwork_refresh_finished,
                updated,
                None,
            )
        except Exception as exc:
            AppHelper.callAfter(self._artwork_refresh_finished, 0, exc)

    @objc.python_method
    def _artwork_refresh_finished(
        self,
        updated: int,
        error: Exception | None,
    ) -> None:
        if error is not None:
            _log(traceback.format_exc())
            self.updateStatusMessage_("Artwork update failed")
            return

        self.reload_library_()
        if updated:
            self.updateStatusMessage_(f"Updated artwork for {updated} games")
        else:
            self.updateStatusMessage_("Library artwork is up to date")

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
                AppHelper.callAfter(self.updateStatusMessage_, message)

            entry, warning = self.library.add_game_from_folder(folder, progress=progress)
            AppHelper.callAfter(self._import_finished, entry, None, warning)
        except Exception as exc:
            AppHelper.callAfter(self._import_finished, None, exc, None)

    @objc.python_method
    def _import_finished(
        self,
        entry: GameEntry | None,
        error: Exception | None,
        warning: str | None,
    ) -> None:
        if error is not None:
            self._show_error("Import Failed", str(error))
            self.updateStatusMessage_("Import failed")
            _log(traceback.format_exc())
            return

        self.reload_library_()
        if warning:
            self._show_error("Imported With Warnings", warning)
            self.updateStatusMessage_(f"Added {entry.title} (see warning)")
        else:
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

        AppHelper.callAfter(self.updateStatusMessage_, message)

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
