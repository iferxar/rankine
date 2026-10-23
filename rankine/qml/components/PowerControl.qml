import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ControlTile {
    id: root
    property string card
    property var power: ({ cap: 0, min: 0, max: 1, default: 0 })
    property real target: NaN  // what the user dragged to, until the card reports it
    readonly property real shown: isNaN(target) ? power.cap : target

    onPowerChanged: if (!isNaN(target) && Math.round(power.cap) === Math.round(target)) target = NaN

    title: "Power limit"
    status: Math.round(power.cap) + " W"
    statusColor: Theme.mint

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        Slider {
            id: slider
            Layout.fillWidth: true
            from: root.power.min
            to: Math.max(root.power.max, root.power.min + 1)
            stepSize: 1
            // Mentioning from/to re-evaluates the binding when the range arrives after the value,
            // which would otherwise leave the value clamped to the placeholder range.
            value: Math.max(from, Math.min(to, root.shown))
            enabled: !tuner.busy
            onMoved: root.target = value
            background: Rectangle {
                x: slider.leftPadding
                y: slider.topPadding + slider.availableHeight / 2 - height / 2
                width: slider.availableWidth
                height: 6
                radius: 3
                color: Theme.track
                Rectangle {
                    width: slider.visualPosition * parent.width
                    height: parent.height
                    radius: 3
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: Theme.teal }
                        GradientStop { position: 1.0; color: Theme.cyan }
                    }
                }
            }
            handle: Rectangle {
                x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
                y: slider.topPadding + slider.availableHeight / 2 - height / 2
                width: 16; height: 16; radius: 8
                color: "#ffffff"
                border.color: Theme.cyan
                border.width: 2
            }
        }
        Text {
            text: Math.round(root.shown) + " W"
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 14
            font.weight: Font.Bold
            font.features: { "tnum": 1 }
            Layout.preferredWidth: 52
            horizontalAlignment: Text.AlignRight
        }
    }
    RowLayout {
        Layout.fillWidth: true
        spacing: 8
        Text {
            text: "Range " + Math.round(root.power.min) + "–" + Math.round(root.power.max) + " W · default "
                  + Math.round(root.power.default) + " W"
            color: Theme.dim
            font.family: Theme.fontFamily
            font.pixelSize: 11
            Layout.fillWidth: true
        }
        PillButton {
            text: "Default"
            visible: Math.round(root.shown) !== Math.round(root.power.default)
            onClicked: root.target = root.power.default
        }
        PillButton {
            text: "Apply"
            outlined: true
            accent: Theme.mint
            visible: !isNaN(root.target) && Math.round(root.target) !== Math.round(root.power.cap)
            onClicked: tuner.setPowerLimit(root.card, Math.round(root.target))
        }
    }
}
