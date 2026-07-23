-- license:BSD-3-Clause
local exports = {
	name = "slot_saves",
	version = "1.1.0",
	description = "OpenEmu-style rotating save slots (Cmd+S save, Cmd+L load)",
	license = "BSD-3-Clause",
	author = { name = "robocop2j-emulator" }
}

local slot_saves = exports

local NUM_SLOTS = 8
local frame_count = 0
local MIN_FRAMES = 60

local slot_dir = nil
local manifest_path = nil
local states_dir = nil
local ack_path = nil
local command_path = nil

local save_seqs = {}
local load_seqs = {}
local save_was_pressed = false
local load_was_pressed = false
local hotkeys_ready = false

local last_command_mtime = 0
local pending_action = nil
local pending_file = nil

local function get_env(name)
	local value = os.getenv(name)
	if value == nil or value == "" then
		return nil
	end
	return value
end

local function utc_now()
	return os.date("!%Y-%m-%dT%H:%M:%SZ")
end

local function default_manifest()
	local slots = {}
	for slot_id = 0, NUM_SLOTS - 1 do
		slots[#slots + 1] = {
			id = slot_id,
			file = string.format("slot_%d", slot_id),
			timestamp = nil,
		}
	end
	return {
		game_id = slot_dir and slot_dir:match("([^/]+)$") or "game",
		slots = slots,
	}
end

local function read_file(path)
	local handle = io.open(path, "r")
	if handle == nil then
		return nil
	end
	local content = handle:read("*a")
	handle:close()
	return content
end

local function write_file(path, content)
	local handle = io.open(path, "w")
	if handle == nil then
		return false
	end
	handle:write(content)
	handle:close()
	return true
end

local function load_manifest()
	if manifest_path == nil then
		return default_manifest()
	end

	local content = read_file(manifest_path)
	if content == nil or content == "" then
		local manifest = default_manifest()
		slot_saves.save_manifest(manifest)
		return manifest
	end

	local ok, manifest = pcall(function()
		local json = require("json")
		return json.parse(content)
	end)
	if not ok or manifest == nil or manifest.slots == nil then
		local manifest = default_manifest()
		slot_saves.save_manifest(manifest)
		return manifest
	end

	if #manifest.slots ~= NUM_SLOTS then
		manifest = default_manifest()
		slot_saves.save_manifest(manifest)
	end

	return manifest
end

function slot_saves.save_manifest(manifest)
	if manifest_path == nil then
		return
	end
	local json = require("json")
	write_file(manifest_path, json.stringify(manifest, { indent = true }) .. "\n")
end

local function state_file_path(file)
	return states_dir .. "/" .. file .. ".sta"
end

local function legacy_state_file_path(file)
	if slot_dir == nil then
		return nil
	end
	local game_id = slot_dir:match("([^/]+)$")
	if game_id == nil then
		return nil
	end
	return states_dir .. "/" .. game_id .. "/" .. file .. ".sta"
end

local function state_exists(file)
	local attrs = lfs.attributes(state_file_path(file))
	if attrs ~= nil then
		return true
	end
	local legacy = legacy_state_file_path(file)
	if legacy == nil then
		return false
	end
	return lfs.attributes(legacy) ~= nil
end

local function pick_save_slot(manifest)
	local empty = {}
	for _, slot in ipairs(manifest.slots) do
		if slot.timestamp == nil then
			empty[#empty + 1] = slot
		end
	end
	if #empty > 0 then
		return empty[1]
	end

	local oldest = manifest.slots[1]
	for _, slot in ipairs(manifest.slots) do
		if slot.timestamp ~= nil and slot.timestamp < oldest.timestamp then
			oldest = slot
		end
	end
	return oldest
end

local function pick_load_slot(manifest)
	local saved = {}
	for _, slot in ipairs(manifest.slots) do
		if slot.timestamp ~= nil and state_exists(slot.file) then
			saved[#saved + 1] = slot
		end
	end
	if #saved == 0 then
		return nil
	end

	local newest = saved[1]
	for _, slot in ipairs(saved) do
		if slot.timestamp > newest.timestamp then
			newest = slot
		end
	end
	return newest
end

local function write_ack(action, file, ok, message)
	if ack_path == nil then
		return
	end
	local status = ok and "ok" or "error"
	local line = string.format(
		'{"action":"%s","file":"%s","status":"%s","message":"%s"}',
		action,
		file,
		status,
		message or ""
	)
	write_file(ack_path, line)
end

local function show_message(message)
	manager.machine:popmessage(message)
	emu.print_info(message)
end

local function perform_save()
	if frame_count < MIN_FRAMES then
		show_message("Please wait for the game to finish loading")
		return
	end
	local manifest = load_manifest()
	local slot = pick_save_slot(manifest)
	local file = slot.file

	manager.machine:save(file)
	slot.timestamp = utc_now()
	slot_saves.save_manifest(manifest)

	local message = string.format("Saved to slot %d/%d", slot.id + 1, NUM_SLOTS)
	show_message(message)
	write_ack("save", file, true, message)
end

local function perform_load()
	if frame_count < MIN_FRAMES then
		show_message("Please wait for the game to finish loading")
		return
	end
	local manifest = load_manifest()
	local slot = pick_load_slot(manifest)
	if slot == nil then
		local message = "No save states found"
		show_message(message)
		write_ack("load", "", false, message)
		return
	end

	manager.machine:load(slot.file)
	local message = string.format(
		"Loaded slot %d/%d (newest save)",
		slot.id + 1,
		NUM_SLOTS
	)
	show_message(message)
	write_ack("load", slot.file, true, message)
end

local function parse_command(content)
	local action = content:match('"action"%s*:%s*"([^"]+)"')
	local file = content:match('"file"%s*:%s*"([^"]+)"')
	if action == nil or file == nil then
		return nil, nil
	end
	return action, file
end

local function read_command()
	if command_path == nil then
		return
	end

	local attrs = lfs.attributes(command_path)
	if attrs == nil then
		return
	end
	if attrs.modification <= last_command_mtime then
		return
	end

	last_command_mtime = attrs.modification
	local content = read_file(command_path)
	if content == nil then
		return
	end
	os.remove(command_path)

	local action, file = parse_command(content)
	if action == nil then
		return
	end

	pending_action = action
	pending_file = file
end

local function process_pending_command()
	if pending_action == nil then
		return
	end

	local action = pending_action
	local file = pending_file
	pending_action = nil
	pending_file = nil

	if action == "save" then
		local manifest = load_manifest()
		local slot = nil
		for _, candidate in ipairs(manifest.slots) do
			if candidate.file == file then
				slot = candidate
				break
			end
		end
		if slot == nil then
			write_ack(action, file, false, "unknown slot")
			return
		end
		manager.machine:save(file)
		slot.timestamp = utc_now()
		slot_saves.save_manifest(manifest)
		write_ack(action, file, true, "saved")
	elseif action == "load" then
		if not state_exists(file) then
			write_ack(action, file, false, "missing save")
			return
		end
		manager.machine:load(file)
		write_ack(action, file, true, "loaded")
	else
		write_ack(action, file, false, "unknown action")
	end
end

local function seq_triggered(input, seqs, was_pressed)
	local pressed = false
	for _, seq in ipairs(seqs) do
		if input:seq_pressed(seq) then
			pressed = true
			break
		end
	end
	local triggered = pressed and not was_pressed
	return triggered, pressed
end

local function ensure_hotkeys()
	if hotkeys_ready then
		return true
	end
	if manager.machine == nil or manager.machine.input == nil then
		return false
	end

	local input = manager.machine.input
	local save_tokens = {
		"KEYCODE_LWIN KEYCODE_S",
		"KEYCODE_RWIN KEYCODE_S",
		"KEYCODE_LWIN KEYCODE_LSHIFT KEYCODE_S",
		"KEYCODE_RWIN KEYCODE_LSHIFT KEYCODE_S",
	}
	local load_tokens = {
		"KEYCODE_LWIN KEYCODE_L",
		"KEYCODE_RWIN KEYCODE_L",
		"KEYCODE_LWIN KEYCODE_LSHIFT KEYCODE_L",
		"KEYCODE_RWIN KEYCODE_LSHIFT KEYCODE_L",
	}

	for _, tokens in ipairs(save_tokens) do
		local seq = input:seq_from_tokens(tokens)
		if seq ~= nil then
			save_seqs[#save_seqs + 1] = seq
		end
	end
	for _, tokens in ipairs(load_tokens) do
		local seq = input:seq_from_tokens(tokens)
		if seq ~= nil then
			load_seqs[#load_seqs + 1] = seq
		end
	end

	hotkeys_ready = #save_seqs > 0 and #load_seqs > 0
	return hotkeys_ready
end

local function process_hotkeys()
	if not ensure_hotkeys() then
		return
	end

	local input = manager.machine.input
	local save_triggered, save_pressed = seq_triggered(input, save_seqs, save_was_pressed)
	local load_triggered, load_pressed = seq_triggered(input, load_seqs, load_was_pressed)
	save_was_pressed = save_pressed
	load_was_pressed = load_pressed

	if save_triggered then
		perform_save()
	elseif load_triggered then
		perform_load()
	end
end

local function process_frame()
	frame_count = frame_count + 1
	read_command()
	process_pending_command()
	process_hotkeys()
end

function slot_saves.startplugin()
	slot_dir = get_env("MAME_SLOT_DIR")
	command_path = get_env("MAME_SLOT_CMD")
	ack_path = get_env("MAME_SLOT_ACK")

	if slot_dir ~= nil then
		manifest_path = slot_dir .. "/manifest.json"
		states_dir = slot_dir .. "/states"
		lfs.mkdir(slot_dir)
		lfs.mkdir(states_dir)
	end

	frame_subscription = emu.add_machine_frame_notifier(process_frame)
	emu.print_info("Slot saves ready: Cmd+S save, Cmd+L load (OpenEmu-style)")
end

return exports
