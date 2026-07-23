"""Editable controller mapping window."""

from __future__ import annotations

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSColor,
    NSFont,
    NSMakeRect,
    NSMakeSize,
    NSScrollView,
    NSTableColumn,
    NSTableView,
    NSTableViewGridNone,
    NSTextAlignmentCenter,
    NSTextField,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject

from emulator.controller import (
    CONTROLLER_ACTIONS,
    ControllerProfile,
    format_key_label,
    mame_key_from_event,
)


class KeyCaptureView(NSView):
    controller = objc.ivar("controller")

    def initWithFrame_controller_(self, frame, controller):
        self = objc.super(KeyCaptureView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.controller = controller
        return self

    def acceptsFirstResponder(self):
        return True

    def keyDown_(self, event):
        if self.controller is None:
            return
        if event.keyCode() == 53:
            self.controller._cancel_capture()
            return
        key = mame_key_from_event(event.keyCode(), event.charactersIgnoringModifiers())
        if key is not None:
            self.controller._capture_key(key)

    def drawRect_(self, rect):
        pass


class ControllerTableDataSource(NSObject):
    rows = objc.ivar("rows")
    profile = objc.ivar("profile")

    def numberOfRowsInTableView_(self, table_view):
        return len(self.rows)

    def tableView_objectValueForTableColumn_row_(self, table_view, column, row):
        action = self.rows[row]
        column_id = column.identifier()
        if column_id == "group":
            if row == 0 or self.rows[row - 1].group != action.group:
                return action.group
            return ""
        if column_id == "label":
            return action.label
        if column_id == "key":
            return format_key_label(self.profile.get_binding(action.action_id))
        return ""

    def tableView_willDisplayCell_forTableColumn_row_(self, table_view, cell, column, row):
        if column.identifier() == "key":
            cell.setAlignment_(NSTextAlignmentCenter)


class ControllerEditorController(NSObject):
    profile = objc.ivar("profile")
    window = objc.ivar("window")
    table_view = objc.ivar("table_view")
    data_source = objc.ivar("data_source")
    status_label = objc.ivar("status_label")
    capture_view = objc.ivar("capture_view")
    capture_action_id = objc.ivar("capture_action_id")
    change_button = objc.ivar("change_button")
    save_button = objc.ivar("save_button")

    def init(self):
        self = objc.super(ControllerEditorController, self).init()
        if self is None:
            return None
        self.profile = ControllerProfile.load()
        self.capture_action_id = None
        self._build_window()
        self.refreshTable()
        return self

    @objc.python_method
    def _build_window(self) -> None:
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, 680, 720),
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskResizable,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Controller Setup")
        self.window.center()
        self.window.setMinSize_(NSMakeSize(620, 560))

        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 680, 720))
        self.window.setContentView_(content)

        title = NSTextField.labelWithString_("Laptop Controller Mapping")
        title.setFrame_(NSMakeRect(20, 680, 640, 24))
        title.setFont_(NSFont.boldSystemFontOfSize_(18))
        content.addSubview_(title)

        subtitle = NSTextField.labelWithString_(
            "Select a control, click Change Key, then press any keyboard key."
        )
        subtitle.setFrame_(NSMakeRect(20, 658, 640, 18))
        subtitle.setFont_(NSFont.systemFontOfSize_(12))
        subtitle.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(subtitle)

        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(20, 120, 640, 520))
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(False)
        scroll.setBorderType_(1)
        scroll.setDrawsBackground_(True)

        self.table_view = NSTableView.alloc().initWithFrame_(NSMakeRect(0, 0, 620, 520))
        self.table_view.setGridStyleMask_(NSTableViewGridNone)
        self.table_view.setAllowsMultipleSelection_(False)
        self.table_view.setRowHeight_(24.0)
        self.table_view.setTarget_(self)
        self.table_view.setDoubleAction_("beginCapture:")

        group_col = NSTableColumn.alloc().initWithIdentifier_("group")
        group_col.setWidth_(110)
        group_col.headerCell().setStringValue_("Section")
        self.table_view.addTableColumn_(group_col)

        label_col = NSTableColumn.alloc().initWithIdentifier_("label")
        label_col.setWidth_(220)
        label_col.headerCell().setStringValue_("Control")
        self.table_view.addTableColumn_(label_col)

        key_col = NSTableColumn.alloc().initWithIdentifier_("key")
        key_col.setWidth_(160)
        key_col.headerCell().setStringValue_("Key")
        self.table_view.addTableColumn_(key_col)

        self.data_source = ControllerTableDataSource.alloc().init()
        self.data_source.rows = list(CONTROLLER_ACTIONS)
        self.data_source.profile = self.profile
        self.table_view.setDataSource_(self.data_source)
        scroll.setDocumentView_(self.table_view)
        content.addSubview_(scroll)

        self.capture_view = KeyCaptureView.alloc().initWithFrame_controller_(
            NSMakeRect(0, 0, 1, 1), self
        )
        content.addSubview_(self.capture_view)

        self.status_label = NSTextField.labelWithString_("Ready")
        self.status_label.setFrame_(NSMakeRect(20, 82, 640, 18))
        self.status_label.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(self.status_label)

        self.change_button = NSButton.alloc().initWithFrame_(NSMakeRect(20, 40, 120, 28))
        self.change_button.setTitle_("Change Key")
        self.change_button.setBezelStyle_(NSBezelStyleRounded)
        self.change_button.setTarget_(self)
        self.change_button.setAction_("beginCapture:")
        content.addSubview_(self.change_button)

        reset_button = NSButton.alloc().initWithFrame_(NSMakeRect(150, 40, 120, 28))
        reset_button.setTitle_("Reset Defaults")
        reset_button.setBezelStyle_(NSBezelStyleRounded)
        reset_button.setTarget_(self)
        reset_button.setAction_("resetDefaults:")
        content.addSubview_(reset_button)

        self.save_button = NSButton.alloc().initWithFrame_(NSMakeRect(280, 40, 90, 28))
        self.save_button.setTitle_("Save")
        self.save_button.setBezelStyle_(NSBezelStyleRounded)
        self.save_button.setTarget_(self)
        self.save_button.setAction_("saveProfile:")
        self.save_button.setEnabled_(True)
        content.addSubview_(self.save_button)

        close_button = NSButton.alloc().initWithFrame_(NSMakeRect(570, 40, 90, 28))
        close_button.setTitle_("Close")
        close_button.setBezelStyle_(NSBezelStyleRounded)
        close_button.setTarget_(self)
        close_button.setAction_("closeWindow:")
        content.addSubview_(close_button)

    @objc.python_method
    def refreshTable(self) -> None:
        self.data_source.profile = self.profile
        self.table_view.reloadData()

    @objc.python_method
    def _selected_action_id(self) -> str | None:
        row = self.table_view.selectedRow()
        if row < 0 or row >= len(CONTROLLER_ACTIONS):
            return None
        return CONTROLLER_ACTIONS[row].action_id

    def show(self) -> None:
        self.window.makeKeyAndOrderFront_(None)
        self.table_view.selectRowIndexes_byExtending_(0, False)
        self.table_view.scrollRowToVisible_(0)

    def resetDefaults_(self, sender) -> None:
        self._cancel_capture()
        self.profile.reset_defaults()
        self.refreshTable()
        self.status_label.setStringValue_("Restored default laptop mappings")

    def saveProfile_(self, sender) -> None:
        self._cancel_capture()
        self.profile.save()
        self.status_label.setStringValue_("Controller saved")

    def closeWindow_(self, sender) -> None:
        self._cancel_capture()
        self.window.orderOut_(None)

    def beginCapture_(self, sender) -> None:
        action_id = self._selected_action_id()
        if action_id is None:
            self.status_label.setStringValue_("Select a control from the list first")
            return
        self.capture_action_id = action_id
        label = next(a.label for a in CONTROLLER_ACTIONS if a.action_id == action_id)
        group = next(a.group for a in CONTROLLER_ACTIONS if a.action_id == action_id)
        self.status_label.setStringValue_(
            f"Listening for {group} / {label}... (Esc to cancel)"
        )
        self.window.makeFirstResponder_(self.capture_view)

    @objc.python_method
    def _capture_key(self, key: str) -> None:
        if self.capture_action_id is None:
            return
        action_id = self.capture_action_id
        self.capture_action_id = None
        self.profile.set_binding(action_id, key)
        self.refreshTable()
        self.status_label.setStringValue_(
            f"Mapped to {format_key_label(key)}. Click Save to apply in MAME."
        )
        self.window.makeFirstResponder_(self.table_view)

    @objc.python_method
    def _cancel_capture(self) -> None:
        self.capture_action_id = None
        if self.window.firstResponder() == self.capture_view:
            self.window.makeFirstResponder_(self.table_view)


def show_controller_editor() -> ControllerEditorController:
    editor = ControllerEditorController.alloc().init()
    editor.show()
    return editor
