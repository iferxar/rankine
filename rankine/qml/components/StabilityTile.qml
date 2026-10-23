import QtQuick
import QtQuick.Layouts

// A timed run of the user's own GPU load while rankine-tuned watches the kernel log for hangs.
ControlTile {
    id: root
    property var stability: ({})
    property bool watching: false
    property int minutes: 15
    readonly property bool running: !!stability.running
    readonly property var verdicts: ({
        passed: ["Passed", Theme.mint, "No GPU hang during the run. Keep the settings, or test longer with a heavier load."],
        failed: ["Failed", Theme.red, "The GPU hung. Rankine restored the original clocks, voltage and power. Back off the last step."],
        inconclusive: ["Inconclusive", Theme.amber, "The GPU was under load for less than half of the run. Start a game or benchmark first."],
        stopped: ["Stopped", Theme.muted, "Stopped before the end."]
    })
    readonly property var verdict: verdicts[stability.verdict] || null

    function mmss(s) { return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0") }

    title: "Stability test"
    status: running ? mmss(stability.elapsed) + " / " + mmss(stability.duration)
                    : verdict ? verdict[0] : ""
    statusColor: running ? Theme.amber : verdict ? verdict[1] : Theme.muted

    Text {
        text: watching
              ? "Start a game or GPU benchmark, then start the test. Rankine counts the time the GPU spends "
                + "above 80 % load and watches the kernel log for GPU hangs and resets."
              : "GPU hang detection is not available: rankine-tuned cannot read the kernel log."
        color: watching ? Theme.muted : Theme.amber
        font.family: Theme.fontFamily
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    Rectangle {
        visible: root.running
        Layout.fillWidth: true
        implicitHeight: 6
        radius: 3
        color: Theme.track
        Rectangle {
            width: parent.width * Math.min(1, (root.stability.elapsed || 0) / (root.stability.duration || 1))
            height: parent.height
            radius: 3
            color: Theme.amber
        }
    }
    Text {
        visible: root.running || !!root.verdict
        text: "Under load " + root.mmss(root.stability.loaded || 0) + " · GPU hangs " + (root.stability.faults || 0)
              + (root.verdict && !root.running ? "\n" + root.verdict[2] : "")
        color: Theme.text
        font.family: Theme.fontFamily
        font.pixelSize: 12
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: [5, 15, 30]
            delegate: PillButton {
                required property int modelData
                visible: !root.running
                text: modelData + " min"
                outlined: root.minutes === modelData
                accent: root.minutes === modelData ? Theme.mint : Theme.muted
                onClicked: root.minutes = modelData
            }
        }
        Item { Layout.fillWidth: true }
        PillButton {
            text: root.running ? "Stop" : "Start test"
            outlined: !root.running
            accent: root.running ? Theme.text : Theme.mint
            enabled: root.watching || root.running
            onClicked: root.running ? tuner.stopStability() : tuner.startStability(root.minutes)
        }
    }
}
