import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

// Read-only overview of what Rankine could tune on this machine (roadmap phase 0).
ScrollView {
    id: page
    contentWidth: availableWidth

    readonly property var t: backend.tuning
    readonly property var helper: t.helper || ({})
    readonly property var helperFeature: helper.running
        ? { title: "Helper service", state: "ready",
            detail: "rankine-tuned is running on the " + helper.bus + " bus. It does not change any settings yet." }
        : helper.installed
        ? { title: "Helper service", state: "setup",
            detail: "rankine-tuned is installed but not running. This page works without it; tuning will need it.",
            command: "sudo systemctl enable --now rankine-tuned.service" }
        : { title: "Helper service", state: "setup",
            detail: "rankine-tuned is not installed. This page works without it; tuning will need it.",
            fix: "From the Rankine checkout, install the system files, then enable the service:",
            command: "sudo ./scripts/install-tuned.sh && sudo systemctl enable --now rankine-tuned.service" }

    Item {
        width: page.availableWidth
        implicitHeight: grid.implicitHeight + 32

        GridLayout {
            id: grid
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 16 }
            columns: width > 1000 ? 2 : 1
            columnSpacing: 16
            rowSpacing: 16
            uniformCellWidths: true

            Card {
                title: "Tuning"
                subtitle: "PREVIEW · NOTHING IS CHANGED"
                subtitleColor: Theme.amber
                Layout.columnSpan: grid.columns
                Layout.fillWidth: true

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    Text {
                        text: "What Rankine will be able to tune on this machine, and what each feature still needs. "
                            + "Versions refer to the roadmap in docs/TUNING.md."
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    PillButton { text: "Refresh"; onClicked: backend.refreshTuning() }
                }
                FeatureRow { feature: page.helperFeature }
            }

            Repeater {
                model: page.t.gpus || []
                delegate: Card {
                    required property var modelData
                    title: "Graphics"
                    subtitle: modelData.name
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.alignment: Qt.AlignTop
                    Repeater {
                        model: modelData.features
                        delegate: FeatureRow { required property var modelData; feature: modelData }
                    }
                }
            }

            Card {
                visible: !!page.t.cpu
                title: "Processor"
                subtitle: page.t.cpu ? page.t.cpu.name + (page.t.cpu.codename ? " · " + page.t.cpu.codename : "") : ""
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                Repeater {
                    model: page.t.cpu ? page.t.cpu.features : []
                    delegate: FeatureRow { required property var modelData; feature: modelData }
                }
            }

            Card {
                visible: (page.t.tools || []).length > 0
                title: "Stability testing"
                subtitle: "TOOLS"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                Repeater {
                    model: page.t.tools || []
                    delegate: FeatureRow { required property var modelData; feature: modelData }
                }
            }
        }
    }
}
