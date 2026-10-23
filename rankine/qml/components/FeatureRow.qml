import QtQuick
import QtQuick.Layouts

// One capability from the tuning probe: state, what it is, and how to enable it.
Rectangle {
    id: root
    property var feature: ({})
    readonly property string state_: feature.state || "unsupported"
    readonly property color stateColor: state_ === "ready" ? Theme.mint
                                      : state_ === "setup" ? Theme.amber
                                      : state_ === "optional" ? Theme.cyan : Theme.dim
    readonly property string stateText: ({ ready: "Available", setup: "Needs setup",
                                           optional: "Optional", unsupported: "Not supported" })[state_] || state_

    color: Theme.tile
    radius: 10
    border.color: Theme.border
    implicitHeight: column.implicitHeight + 20
    Layout.fillWidth: true

    ColumnLayout {
        id: column
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 10; leftMargin: 12 }
        spacing: 4

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            Rectangle { width: 8; height: 8; radius: 4; color: root.stateColor }
            Text {
                text: root.feature.title || ""
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 13
                font.weight: Font.Bold
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Text {
                visible: !!root.feature.phase
                text: "v" + root.feature.phase
                color: Theme.dim
                font.family: Theme.fontFamily
                font.pixelSize: 11
            }
            Text {
                text: root.stateText.toUpperCase()
                color: root.stateColor
                font.family: Theme.fontFamily
                font.pixelSize: 11
                font.weight: Font.DemiBold
                font.letterSpacing: 0.8
            }
        }
        Text {
            text: root.feature.detail || ""
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Layout.leftMargin: 16
        }
        Text {
            visible: !!root.feature.fix
            text: root.feature.fix || ""
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 12
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            Layout.leftMargin: 16
        }
        Rectangle {
            visible: !!root.feature.command
            Layout.fillWidth: true
            Layout.leftMargin: 16
            Layout.topMargin: 2
            implicitHeight: commandRow.implicitHeight + 10
            radius: 6
            color: Theme.bgDeep
            border.color: Theme.border

            RowLayout {
                id: commandRow
                anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter
                          leftMargin: 10; rightMargin: 4 }
                TextEdit {
                    id: command
                    text: root.feature.command || ""
                    readOnly: true
                    selectByMouse: true
                    color: Theme.mint
                    selectionColor: Theme.tealDeep
                    font.family: "monospace"
                    font.pixelSize: 12
                    wrapMode: TextEdit.WrapAnywhere
                    Layout.fillWidth: true
                }
                PillButton {
                    id: copy
                    property bool copied: false
                    text: copied ? "Copied" : "Copy"
                    implicitHeight: 24
                    onClicked: {
                        command.selectAll(); command.copy(); command.deselect()
                        copied = true
                        resetCopied.restart()
                    }
                    Timer { id: resetCopied; interval: 1500; onTriggered: copy.copied = false }
                }
            }
        }
    }
}
