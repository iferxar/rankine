import QtQuick
import QtQuick.Layouts

// Average readings over the 20 s before a change and the 20 s after it.
ControlTile {
    id: root
    property var comparison: ({})
    readonly property var rows: [
        ["gpu.power", "Power", " W", 1, true],
        ["gpu.temp", "Temperature", " °C", 1, true],
        ["gpu.hotspot", "Hotspot", " °C", 1, true],
        ["gpu.mhz", "Clock", " MHz", 0, false],
        ["gpu.fan_rpm", "Fan", " RPM", 0, true],
        ["gpu.load", "Load", " %", 0, false],
    ]

    title: "Before / after"
    status: comparison.collected < comparison.needed
            ? "Measuring " + comparison.collected + " / " + comparison.needed + " s" : "Done"
    statusColor: comparison.collected < comparison.needed ? Theme.amber : Theme.mint

    Text {
        text: (comparison.what || "") + ". Keep the same load running before and after for a fair comparison."
        color: Theme.muted
        font.family: Theme.fontFamily
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    GridLayout {
        Layout.fillWidth: true
        columns: 4
        columnSpacing: 14
        rowSpacing: 4
        Repeater {
            model: ["", "BEFORE", "AFTER", "CHANGE"]
            delegate: Text {
                required property string modelData
                required property int index
                text: modelData
                color: Theme.dim
                font.family: Theme.fontFamily
                font.pixelSize: 10
                font.weight: Font.DemiBold
                font.letterSpacing: 0.8
                Layout.fillWidth: index === 0
                horizontalAlignment: index === 0 ? Text.AlignLeft : Text.AlignRight
            }
        }
        Repeater {
            model: root.rows.length * 4
            delegate: Text {
                required property int index
                readonly property var r: root.rows[Math.floor(index / 4)]
                readonly property int col: index % 4
                readonly property var b: (root.comparison.before || {})[r[0]]
                readonly property var a: (root.comparison.after || {})[r[0]]
                readonly property bool both: b !== undefined && a !== undefined
                // lower is better for power, temperatures and fan noise
                readonly property real delta: both ? a - b : 0
                text: col === 0 ? r[1]
                    : col === 1 ? Theme.fmt(b, r[3], r[2])
                    : col === 2 ? Theme.fmt(a, r[3], r[2])
                    : both ? (delta >= 0 ? "+" : "") + delta.toFixed(r[3]) + r[2] : ""
                color: col === 0 ? Theme.muted : col < 3 ? Theme.text
                     : Math.abs(delta) < 0.05 ? Theme.dim
                     : (delta < 0) === r[4] ? Theme.mint : Theme.amber
                font.family: Theme.fontFamily
                font.pixelSize: 12
                font.weight: col === 3 ? Font.Bold : Font.Normal
                font.features: { "tnum": 1 }
                Layout.fillWidth: col === 0
                horizontalAlignment: col === 0 ? Text.AlignLeft : Text.AlignRight
            }
        }
    }
    RowLayout {
        Layout.fillWidth: true
        Item { Layout.fillWidth: true }
        PillButton { text: "Clear"; onClicked: tuner.clearComparison() }
    }
}
