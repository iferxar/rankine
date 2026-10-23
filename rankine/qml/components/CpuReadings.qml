import QtQuick
import QtQuick.Layouts

// Live values from the SMU power table: package limits and usage, then each core.
ControlTile {
    id: root
    property var table: ({})
    readonly property var usage: [
        ["PPT", table.ppt, table.ppt_limit, "W"],
        ["TDC", table.tdc, table.tdc_limit, "A"],
        ["EDC", table.edc, table.edc_limit, "A"],
    ]

    title: "SMU readings"
    status: Theme.fmt(table.socket_power, 0, " W") + " · " + Theme.fmt(table.thm, 0, " °C")
    statusColor: Theme.mint

    // A count model keeps the rows alive between refreshes, so the bars ease instead of restarting.
    Repeater {
        model: root.usage.length
        delegate: BarRow {
            required property int index
            readonly property var row: root.usage[index]
            label: row[0]
            valueText: Theme.fmt(row[1], 0, " " + row[3]) + " / " + Theme.fmt(row[2], 0, " " + row[3])
            frac: row[2] ? row[1] / row[2] : 0
            colors: Theme.loadGradient(row[2] ? 100 * row[1] / row[2] : 0)
        }
    }
    Text {
        text: "Zen 3 firmware reports EDC near its limit even at idle, so the EDC bar says little."
        color: Theme.dim
        font.family: Theme.fontFamily
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
    GridLayout {
        Layout.fillWidth: true
        columns: 4
        columnSpacing: 6
        rowSpacing: 6
        Repeater {
            model: (root.table.core_voltage || []).length
            delegate: Rectangle {
                required property int index
                readonly property real load: (root.table.core_c0 || [])[index] || 0
                Layout.fillWidth: true
                implicitHeight: cell.implicitHeight + 10
                radius: 6
                color: Theme.bgDeep
                border.color: Theme.border
                Rectangle {  // share of time the core was awake
                    anchors { left: parent.left; bottom: parent.bottom; margins: 1 }
                    height: 2
                    radius: 1
                    width: (parent.width - 2) * Math.min(1, parent.load / 100)
                    color: Theme.cyan
                }
                ColumnLayout {
                    id: cell
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 7; rightMargin: 7 }
                    spacing: 0
                    RowLayout {
                        Text {
                            text: "C" + index
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                        Text {
                            text: Theme.fmt((root.table.core_voltage || [])[index], 3, " V")
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: 12
                            font.weight: Font.Bold
                            font.features: { "tnum": 1 }
                        }
                    }
                    Text {
                        text: Theme.fmt((root.table.core_freq || [])[index], 0, " MHz") + " · "
                              + Theme.fmt((root.table.core_power || [])[index], 1, " W")
                        color: Theme.dim
                        font.family: Theme.fontFamily
                        font.pixelSize: 10
                        font.features: { "tnum": 1 }
                    }
                }
            }
        }
    }
    Text {
        text: "Per core: voltage, effective clock (averaged with the time asleep) and power; the line is the share of time awake."
        color: Theme.dim
        font.family: Theme.fontFamily
        font.pixelSize: 11
        wrapMode: Text.WordWrap
        Layout.fillWidth: true
    }
}
