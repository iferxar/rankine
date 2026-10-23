import QtQuick
import QtQuick.Layouts

// Save the current settings to be applied at every boot, once they are proven.
ControlTile {
    id: root
    property string card
    property var live: ({})          // this card's GetState entry
    property var profile: ({})       // GetState boot_profile
    property bool tested: false      // current settings passed a stability test in this session
    property bool pending: false     // an unconfirmed change is waiting
    readonly property var saved: (profile.cards || {})[card] || null
    readonly property bool current: !!live.is_boot_profile
    readonly property bool needsTest: !!live.risky && !tested && !current

    function summary(state) {
        if (!state) return ""
        const s = state.snap || {}, od = s.od || {}, parts = []
        if (s.power_uw) parts.push(Math.round(s.power_uw / 1e6) + " W")
        if (od.sclk_max) parts.push(od.sclk_max + " MHz core")
        if (od.mclk_max) parts.push(od.mclk_max + " MHz memory")
        if (od.voltage_offset !== undefined && od.voltage_offset !== null) parts.push(od.voltage_offset + " mV")
        if (s.level) parts.push("level " + s.level)
        parts.push(state.fan_points ? "fan curve" : "firmware fan")
        return parts.join(" · ")
    }

    title: "Apply at boot"
    status: !saved ? "Off" : profile.enabled ? "On" : "Turned off"
    statusColor: !saved ? Theme.muted : profile.enabled ? Theme.mint : Theme.amber

    Text {
        visible: !!root.saved
        text: "Saved " + (root.profile.saved ? new Date(root.profile.saved * 1000).toLocaleString(Qt.locale(), "yyyy-MM-dd HH:mm") : "")
              + ": " + root.summary(root.saved)
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: 12
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        visible: !!root.profile.notice
        text: root.profile.notice || ""
        color: Theme.amber
        font.family: Theme.fontFamily
        font.pixelSize: 12
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Text {
        text: root.pending ? "Keep or revert the current change first."
            : root.current ? (root.profile.enabled ? "The current settings are the boot profile."
                                                   : "The current settings match the saved profile.")
            : root.needsTest ? "These settings raise power or clocks, or undervolt: they need to pass a stability "
                               + "test in this session before they can be applied at boot."
            : "Applies the current settings each time the computer starts. If a session that applied them "
              + "ends in a crash or freeze, or the GPU hangs, the next boot skips them."
        color: root.needsTest || root.pending ? Theme.amber : Theme.muted
        font.family: Theme.fontFamily
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        Item { Layout.fillWidth: true }
        PillButton {
            visible: !!root.saved
            text: "Stop applying at boot"
            onClicked: tuner.clearBootProfile(root.card)
        }
        PillButton {
            visible: !!root.saved && !root.profile.enabled && !root.needsTest
            text: "Turn back on"
            onClicked: tuner.enableBootProfile()
        }
        PillButton {
            visible: !root.current
            text: root.saved ? "Save current settings" : "Apply these settings at boot"
            outlined: true
            accent: Theme.mint
            enabled: !root.needsTest && !root.pending && !tuner.busy
            opacity: enabled ? 1 : 0.45
            onClicked: tuner.saveBootProfile(root.card)
        }
    }
}
