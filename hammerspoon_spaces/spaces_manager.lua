-- ============================================================
-- Author:  Manuel Wenger
-- License: MIT (see LICENSE file or https://opensource.org/licenses/MIT)
--
-- DISCLAIMER: This software is provided "as is", without warranty of any kind.
-- Use at your own risk. The author accepts no liability for any damage or data
-- loss caused by the use of this script.
-- ============================================================
--
-- spaces_manager.lua
-- Hammerspoon script to manage macOS Mission Control spaces.
--
-- Provides hotkeys to:
--   • Move a set of configured "work" apps to a dedicated work space
--   • Move them back to the home space
--   • Hide / unhide a set of "personal" apps (e.g. messaging)
--   • Quit all work apps at once
--   • Dump a full debug report to the Hammerspoon console
--
-- Requirements:
--   • Hammerspoon (https://www.hammerspoon.org) installed and running
--   • macOS Mission Control spaces set up (at least 2 spaces)
--   • Accessibility permissions granted to Hammerspoon
-- ============================================================

-- ============================================================
-- Configuration
-- To retrieve an app bundle ID: osascript -e 'id of app "Name of app"'
-- ============================================================

-- Apps that will be moved between spaces (typically corporate / work apps).
-- Add or remove entries to match your setup.
local WORK_APPS = {
    { bundleID = "com.microsoft.Outlook" },
    { bundleID = "com.microsoft.teams2" },
    { bundleID = "com.microsoft.Excel" },
    { bundleID = "com.microsoft.Word" },
    { bundleID = "com.microsoft.Powerpoint" },
    { bundleID = "com.microsoft.onenote.mac" },
    { bundleID = "com.microsoft.rdc.macos" },  -- Microsoft Remote Desktop
}

-- Apps that will be hidden when switching to work context and
-- unhidden when switching back to personal context.
-- Typically messaging, social, or other personal apps.
local HIDE_APPS = {
    { bundleID = "ru.keepcoder.Telegram" },
    { bundleID = "com.tdesktop.Telegram" },
    { bundleID = "com.apple.Safari.WebApp.F1E47F6F-DB4B-4CD6-BB4A-0EB621FB691F" },  -- Safari web app (e.g. a pinned site)
    { bundleID = "com.BZG.Messenger" },
    { bundleID = "net.whatsapp.WhatsApp" },
    { bundleID = "com.apple.MobileSMS" },   -- macOS Messages
    { bundleID = "com.apple.Notes" },
}

-- Index of the Mission Control space used for work apps (1-based).
local WORK_SPACE_NUMBER = 2

-- Index of the Mission Control space used for personal / home apps (1-based).
local HOME_SPACE_NUMBER = 1

-- ============================================================
-- hideApps / unhideApps
-- Iterate over HIDE_APPS and hide or unhide each running app.
-- Apps that are not currently running are silently skipped.
-- ============================================================
function hideApps()
    for _, app_config in ipairs(HIDE_APPS) do
        local app = hs.application.get(app_config.bundleID)
        if app then
            app:hide()
            print("HIDDEN: " .. app_config.bundleID)
        else
            print("SKIP: " .. app_config.bundleID .. " — not running")
        end
    end
end

function unhideApps()
    for _, app_config in ipairs(HIDE_APPS) do
        local app = hs.application.get(app_config.bundleID)
        if app then
            app:unhide()
            print("UNHIDDEN: " .. app_config.bundleID)
        else
            print("SKIP: " .. app_config.bundleID .. " — not running")
        end
    end
end

-- ============================================================
-- getAllWindowsByBundleID
-- Snapshot ALL open windows (across all spaces) and return them
-- as a table keyed by bundle ID.  Taking the snapshot upfront
-- avoids the index becoming stale while windows are being moved.
-- ============================================================
function getAllWindowsByBundleID()
    local result = {}
    for _, win in ipairs(hs.window.allWindows()) do
        local app = win:application()
        if app then
            local bid = app:bundleID()
            if bid then
                if not result[bid] then result[bid] = {} end
                table.insert(result[bid], win)
            end
        end
    end
    return result
end

-- ============================================================
-- moveAppWindowsToSpace
-- Move all windows of a single app from sourceSpaceNumber to
-- destSpaceNumber, using a simulated mouse-drag via Ctrl+<n>.
--
-- Parameters:
--   bundleID        – the app's bundle identifier string
--   sourceSpaceNumber – the space the window currently lives on
--   destSpaceNumber   – the target space
--   windowIndex     – pre-built table from getAllWindowsByBundleID()
--
-- Returns: number of windows actually moved.
-- ============================================================
function moveAppWindowsToSpace(bundleID, sourceSpaceNumber, destSpaceNumber, windowIndex)
    local wins = windowIndex[bundleID]
    if not wins or #wins == 0 then
        print("SKIP: " .. bundleID .. " — no windows found")
        return 0
    end

    print("MOVING: " .. bundleID .. " — " .. #wins .. " window(s)")
    local moved = 0

    for _, win in ipairs(wins) do
        -- Only process normal, non-minimised windows
        if not win:isMinimized() and win:role() == "AXWindow" then
            print("  window: '" .. (win:title() or "nil") .. "'")

            -- Switch to the source space so the window is visible and focusable
            hs.eventtap.keyStroke({"ctrl"}, tostring(sourceSpaceNumber))
            hs.timer.usleep(300000)  -- 300 ms: wait for space animation

            win:focus()
            hs.timer.usleep(150000)  -- 150 ms: wait for focus to settle

            -- Compute a drag start point near the top-left of the title bar.
            -- We avoid the very edge to stay clear of resize handles.
            local frame = win:frame()
            local point = {
                x = frame.x + math.min(150, frame.w * 0.4),
                y = frame.y + 10
            }

            -- Simulate: press left mouse button → Ctrl+<dest> → release mouse.
            -- macOS interprets this sequence as "drag window to another space".
            hs.eventtap.event.newMouseEvent(hs.eventtap.event.types.leftMouseDown, point):post()
            hs.timer.usleep(100000)  -- 100 ms: hold before keystroke
            hs.eventtap.keyStroke({"ctrl"}, tostring(destSpaceNumber))
            hs.timer.usleep(300000)  -- 300 ms: wait for space to switch
            hs.eventtap.event.newMouseEvent(hs.eventtap.event.types.leftMouseUp, point):post()
            hs.timer.usleep(200000)  -- 200 ms: let macOS register the drop

            moved = moved + 1
            print("  moved ✅")
        end
    end

    return moved
end

-- ============================================================
-- moveAllAppsToSpace
-- Orchestrates moving all WORK_APPS windows to destSpaceNumber.
-- The source space is inferred as the opposite of the destination.
-- A window snapshot is taken once before any moves to keep the
-- index consistent throughout the operation.
-- ============================================================
function moveAllAppsToSpace(destSpaceNumber)
    -- Determine which space the windows are currently on
    local sourceSpaceNumber = destSpaceNumber == WORK_SPACE_NUMBER and HOME_SPACE_NUMBER or WORK_SPACE_NUMBER

    -- Take a single snapshot of all windows before moving anything.
    -- This prevents stale references as windows change spaces.
    local windowIndex = getAllWindowsByBundleID()

    local totalMoved = 0
    for _, app_config in ipairs(WORK_APPS) do
        totalMoved = totalMoved + moveAppWindowsToSpace(app_config.bundleID, sourceSpaceNumber, destSpaceNumber, windowIndex)
        hs.timer.usleep(300000)  -- brief pause between apps to avoid race conditions
    end

    -- Navigate to the destination space after all moves are complete
    hs.eventtap.keyStroke({"ctrl"}, tostring(destSpaceNumber))

    -- Show a brief HUD notification with the result
    if totalMoved > 0 then
        hs.alert.show("✅ Moved " .. totalMoved .. " windows to Space " .. destSpaceNumber)
    else
        hs.alert.show("⚠️ No matching windows found")
    end
end

-- ============================================================
-- quitWorkApps
-- Gracefully quit every app listed in WORK_APPS.
-- Apps that are not running are silently skipped.
-- ============================================================
function quitWorkApps()
    for _, app_config in ipairs(WORK_APPS) do
        local app = hs.application.get(app_config.bundleID)
        if app then
            app:kill()
            print("QUIT: " .. app_config.bundleID)
        else
            print("SKIP: " .. app_config.bundleID .. " — not running")
        end
    end
end

-- ============================================================
-- Hotkeys
-- All hotkeys use the Cmd+Alt+Ctrl modifier ("hyper" chord).
-- ============================================================

-- Move all WORK_APPS to the work space (Space 2)
hs.hotkey.bind({"cmd", "alt", "ctrl"}, "W", function()
    moveAllAppsToSpace(WORK_SPACE_NUMBER)
end)

-- Move all WORK_APPS back to the home space (Space 1)
hs.hotkey.bind({"cmd", "alt", "ctrl"}, "H", function()
    moveAllAppsToSpace(HOME_SPACE_NUMBER)
end)

-- Hide all apps listed in HIDE_APPS
hs.hotkey.bind({"cmd", "alt", "ctrl"}, "X", function()
    hideApps()
end)

-- Unhide all apps listed in HIDE_APPS
hs.hotkey.bind({"cmd", "alt", "ctrl"}, "U", function()
    unhideApps()
end)

-- Quit all WORK_APPS
hs.hotkey.bind({"cmd", "alt", "ctrl"}, "Q", function()
    quitWorkApps()
end)

-- ============================================================
-- Debug hotkey (Cmd+Alt+Ctrl+D)
-- Dumps a full report of running apps, open windows, and space
-- assignments to the Hammerspoon console.  Useful for diagnosing
-- bundle ID mismatches or unexpected window placement.
-- ============================================================
hs.hotkey.bind({"cmd", "alt", "ctrl"}, "D", function()
    print("========== FULL DEBUG ==========")

    print("All running applications:")
    for _, app in ipairs(hs.application.runningApplications()) do
        print("  bundleID='" .. (app:bundleID() or "nil") .. "'"
            .. " name='" .. (app:name() or "nil") .. "'"
            .. " pid=" .. tostring(app:pid()))
    end

    print("")
    print("All visible windows (hs.window.allWindows()):")
    for _, win in ipairs(hs.window.allWindows()) do
        local app = win:application()
        print("  title='" .. (win:title() or "nil") .. "'"
            .. " role=" .. tostring(win:role())
            .. " visible=" .. tostring(win:isVisible())
            .. " minimized=" .. tostring(win:isMinimized())
            .. " bundleID='" .. (app and app:bundleID() or "nil") .. "'"
            .. " appName='" .. (app and app:name() or "nil") .. "'"
            .. " spaces=" .. hs.inspect(hs.spaces.windowSpaces(win)))
    end

    print("")
    print("Spaces info:")
    local allSpaces = hs.spaces.allSpaces()
    print("  allSpaces: " .. hs.inspect(allSpaces))
    for screenUUID, spaceList in pairs(allSpaces) do
        print("  screen: " .. screenUUID)
        for i, spaceID in ipairs(spaceList) do
            print("    index=" .. i .. " spaceID=" .. tostring(spaceID))
        end
    end

    hs.alert.show("Debug output in Hammerspoon console")
end)
