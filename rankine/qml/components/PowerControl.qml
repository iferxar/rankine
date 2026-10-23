import QtQuick
import QtQuick.Layouts

ControlTile {
    id: root
    property string card
    property var power: ({ cap: 0, min: 0, max: 1, default: 0 })

    title: "Power limit"
    status: Math.round(power.cap) + " W"
    statusColor: Theme.mint

    ValueSlider {
        id: limit
        label: "Board power limit"
        unit: "W"
        from: root.power.min
        to: root.power.max
        value: root.power.cap
        defaultValue: root.power.default
    }
    Text {
        visible: Math.round(limit.shown) > Math.round(root.power.default)
        text: "Above the card's default limit: this is overclocking. Raise it in steps and run a stability test."
        color: Theme.amber
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
            text: "Default"
            visible: Math.round(limit.shown) !== Math.round(root.power.default)
            onClicked: limit.target = root.power.default
        }
        PillButton {
            text: "Cancel"
            visible: limit.dirty
            onClicked: limit.target = NaN
        }
        PillButton {
            text: "Apply"
            outlined: true
            accent: Theme.mint
            visible: limit.dirty
            onClicked: tuner.setPowerLimit(root.card, Math.round(limit.target))
        }
    }
}
