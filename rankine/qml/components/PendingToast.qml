import QtQuick
import QtQuick.Layouts

// Shown on every page while a tuning change waits for confirmation.
Rectangle {
    id: root
    property var pending: null
    property real remaining: pending ? pending.remaining : 0

    visible: !!pending
    color: Theme.card
    radius: 12
    border.color: Theme.amber
    border.width: 1.5
    implicitHeight: row.implicitHeight + 20

    // Smooth the countdown between one-second polls.
    onPendingChanged: remaining = pending ? pending.remaining : 0
    Timer {
        running: root.visible
        interval: 200
        repeat: true
        onTriggered: root.remaining = Math.max(0, root.remaining - 0.2)
    }

    RowLayout {
        id: row
        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter
                  leftMargin: 16; rightMargin: 12 }
        spacing: 12
        Text {
            text: Math.ceil(root.remaining)
            color: Theme.amber
            font.family: Theme.fontFamily
            font.pixelSize: 22
            font.weight: Font.Bold
            font.features: { "tnum": 1 }
            Layout.preferredWidth: 28
            horizontalAlignment: Text.AlignHCenter
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Text {
                text: root.pending && root.pending.mine ? "Keep these settings?" : "Another window changed the GPU settings"
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 13
                font.weight: Font.Bold
            }
            Text {
                text: (root.pending ? root.pending.items.join(" · ") : "") + " — reverts automatically unless kept"
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: 11
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }
        PillButton { text: "Revert"; onClicked: tuner.revert() }
        PillButton {
            visible: !!root.pending && root.pending.mine
            text: "Keep"
            outlined: true
            accent: Theme.mint
            onClicked: tuner.confirm()
        }
    }
}
