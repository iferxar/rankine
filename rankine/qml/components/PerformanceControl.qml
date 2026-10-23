import QtQuick
import QtQuick.Layouts

ControlTile {
    id: root
    property string card
    property string level
    property var profiles: []   // [[index, NAME], ...]
    property int profile: -1
    property string pickLevel: ""
    property int pickProfile: -1
    readonly property bool dirty: (pickLevel !== "" && pickLevel !== level)
                                  || (pickProfile >= 0 && pickProfile !== profile)

    onLevelChanged: if (pickLevel === level) pickLevel = ""
    onProfileChanged: if (pickProfile === profile) pickProfile = -1

    function pretty(name) {
        return name.toLowerCase().split("_").map(w => w === "3d" ? "3D" : w.charAt(0).toUpperCase() + w.slice(1)).join(" ")
    }

    title: "Performance"
    status: pretty(level) + " · " + pretty((profiles.find(p => p[0] === profile) || [0, "—"])[1])
    statusColor: Theme.mint

    Text {
        text: "LEVEL"
        color: Theme.dim
        font.family: Theme.fontFamily
        font.pixelSize: 10
        font.weight: Font.DemiBold
        font.letterSpacing: 0.8
    }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: ["auto", "low", "high"]
            delegate: PillButton {
                required property string modelData
                readonly property bool on: (root.pickLevel || root.level) === modelData
                text: root.pretty(modelData)
                outlined: on
                accent: on ? Theme.mint : Theme.muted
                onClicked: root.pickLevel = modelData
            }
        }
    }
    Text {
        text: "PROFILE"
        color: Theme.dim
        font.family: Theme.fontFamily
        font.pixelSize: 10
        font.weight: Font.DemiBold
        font.letterSpacing: 0.8
    }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        Repeater {
            model: root.profiles.length  // a count model survives the state refreshing every second
            delegate: PillButton {
                required property int index
                readonly property var modelData: root.profiles[index]
                readonly property bool on: (root.pickProfile >= 0 ? root.pickProfile : root.profile) === modelData[0]
                text: root.pretty(modelData[1])
                outlined: on
                accent: on ? Theme.mint : Theme.muted
                onClicked: root.pickProfile = modelData[0]
            }
        }
    }
    RowLayout {
        visible: root.dirty
        Layout.fillWidth: true
        Item { Layout.fillWidth: true }
        PillButton {
            text: "Cancel"
            onClicked: { root.pickLevel = ""; root.pickProfile = -1 }
        }
        PillButton {
            text: "Apply"
            outlined: true
            accent: Theme.mint
            onClicked: tuner.setPerformance(root.card,
                                            root.pickLevel !== root.level ? root.pickLevel : "",
                                            root.pickProfile !== root.profile ? root.pickProfile : -1)
        }
    }
}
