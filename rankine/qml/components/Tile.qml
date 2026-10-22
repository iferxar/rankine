import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root
    property string title
    property string value
    property string footer
    property bool estimated: false
    property color valueColor: Theme.text

    color: Theme.tile
    radius: 8
    border.color: Theme.border
    implicitWidth: 120
    implicitHeight: 86
    Layout.fillWidth: true
    Layout.preferredWidth: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 2

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: root.title.toUpperCase()
                color: Theme.muted
                font.pixelSize: 11
                font.weight: Font.DemiBold
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Rectangle {
                visible: root.estimated
                color: "#1d3a52"
                radius: 4
                implicitWidth: est.implicitWidth + 8
                implicitHeight: est.implicitHeight + 2
                Text {
                    id: est
                    anchors.centerIn: parent
                    text: "est."
                    color: Theme.blue
                    font.pixelSize: 10
                }
            }
        }
        Text {
            text: root.value
            color: root.valueColor
            font.pixelSize: 18
            font.weight: Font.Bold
        }
        Item { Layout.fillHeight: true }
        Text {
            text: root.footer
            color: Theme.dim
            font.pixelSize: 10
            Layout.fillWidth: true
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            lineHeight: 0.95
        }
    }
}
