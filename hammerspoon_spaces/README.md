# Hammerspoon Spaces Manager

A [Hammerspoon](https://www.hammerspoon.org) script for macOS that lets you instantly move a defined set of work applications between Mission Control spaces and toggle the visibility of personal/messaging apps — all via keyboard shortcuts.

## Features

- **Move work apps to your work space** with a single hotkey
- **Send them back to your home space** just as easily
- **Hide personal apps** (messaging, notes, etc.) when switching into work mode
- **Unhide them** when you're done
- **Quit all work apps** at once
- **Debug dump** to the Hammerspoon console for troubleshooting

## Requirements

- macOS with Mission Control spaces enabled (at least 2 spaces)
- [Hammerspoon](https://www.hammerspoon.org) installed and running
- Accessibility permissions granted to Hammerspoon (`System Settings → Privacy & Security → Accessibility`)

## Installation

1. Copy `spaces_manager.lua` into your Hammerspoon config directory:
   ```
   ~/.hammerspoon/
   ```
2. If you are using a single `init.lua`, you can either:
   - Rename the file to `init.lua` (replacing any existing one), or
   - Load it from your existing `init.lua`:
     ```lua
     require("spaces_manager")
     ```
3. Reload the Hammerspoon config (`Cmd+Alt+Ctrl+R` or click *Reload Config* in the menu bar icon).

## Configuration

Open `spaces_manager.lua` and edit the tables and constants at the top of the file:

### `WORK_APPS`
List the bundle IDs of apps you want to move between spaces. The default list includes common Microsoft 365 apps and Remote Desktop.

```lua
local WORK_APPS = {
    { bundleID = "com.microsoft.Outlook" },
    { bundleID = "com.microsoft.teams2" },
    -- add more entries here
}
```

### `HIDE_APPS`
List the bundle IDs of personal apps that should be hidden when you switch into work mode.

```lua
local HIDE_APPS = {
    { bundleID = "net.whatsapp.WhatsApp" },
    -- add more entries here
}
```

### Space numbers
```lua
local WORK_SPACE_NUMBER = 2   -- Mission Control index of your work space
local HOME_SPACE_NUMBER = 1   -- Mission Control index of your home space
```

> **Tip — finding a bundle ID:**  
> Run the following in Terminal (replace `Name of app` with the actual app name):
> ```
> osascript -e 'id of app "Name of app"'
> ```
> Or use the **Debug hotkey** (`Cmd+Alt+Ctrl+D`) to dump all running apps and their bundle IDs to the Hammerspoon console.

## Hotkeys

All hotkeys use the **Cmd+Alt+Ctrl** modifier (sometimes called the "hyper" key).

| Hotkey | Action |
|---|---|
| `Cmd+Alt+Ctrl+W` | Move all work apps → **Work space** |
| `Cmd+Alt+Ctrl+H` | Move all work apps → **Home space** |
| `Cmd+Alt+Ctrl+X` | **Hide** all personal apps |
| `Cmd+Alt+Ctrl+U` | **Unhide** all personal apps |
| `Cmd+Alt+Ctrl+Q` | **Quit** all work apps |
| `Cmd+Alt+Ctrl+D` | Dump debug info to Hammerspoon console |

## How it works

Window movement is done by simulating a mouse press on the window's title bar followed by the macOS `Ctrl+<space number>` keyboard shortcut, then releasing the mouse. This replicates the gesture macOS uses to drag a window from one space to another, without triggering Exposé or any visual flash.

A snapshot of all open windows is taken **before** any moves begin, so the index stays consistent throughout the operation.

## Troubleshooting

- **Windows not moving?** Make sure Mission Control keyboard shortcuts for spaces are enabled in `System Settings → Keyboard → Keyboard Shortcuts → Mission Control` and that the shortcuts match the configured space numbers (e.g. `Ctrl+1`, `Ctrl+2`).
- **Bundle ID not found?** Use `Cmd+Alt+Ctrl+D` to see all running apps and their bundle IDs in the Hammerspoon console.
- **Accessibility error?** Make sure Hammerspoon has Accessibility permission under `System Settings → Privacy & Security → Accessibility`.

---

## Disclaimer
This software is provided "as is", without warranty of any kind. Use at your own risk. The author accepts no liability for any damage or data loss caused by the use of this script.

## License
[MIT](../LICENSE) © Manuel Wenger
