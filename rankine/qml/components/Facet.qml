import QtQuick
import QtQuick.Shapes

// Small low-poly hexagon: six triangles from the center in alternating accent shades.
Shape {
    id: root
    property real size: 14
    property var shades: [Theme.cyan, Theme.teal, Theme.mint, Theme.tealDeep, Theme.cyan, Theme.teal]

    implicitWidth: size
    implicitHeight: size
    width: size
    height: size
    preferredRendererType: Shape.CurveRenderer

    readonly property real r: size / 2

    function cx(i) { return r + r * Math.cos(Math.PI / 3 * i - Math.PI / 2) }
    function cy(i) { return r + r * Math.sin(Math.PI / 3 * i - Math.PI / 2) }

    ShapePath {
        strokeWidth: -1
        fillColor: root.shades[0]
        startX: root.r; startY: root.r
        PathLine { x: root.cx(0); y: root.cy(0) }
        PathLine { x: root.cx(1); y: root.cy(1) }
        PathLine { x: root.r; y: root.r }
    }

    ShapePath {
        strokeWidth: -1
        fillColor: root.shades[1]
        startX: root.r; startY: root.r
        PathLine { x: root.cx(1); y: root.cy(1) }
        PathLine { x: root.cx(2); y: root.cy(2) }
        PathLine { x: root.r; y: root.r }
    }

    ShapePath {
        strokeWidth: -1
        fillColor: root.shades[2]
        startX: root.r; startY: root.r
        PathLine { x: root.cx(2); y: root.cy(2) }
        PathLine { x: root.cx(3); y: root.cy(3) }
        PathLine { x: root.r; y: root.r }
    }

    ShapePath {
        strokeWidth: -1
        fillColor: root.shades[3]
        startX: root.r; startY: root.r
        PathLine { x: root.cx(3); y: root.cy(3) }
        PathLine { x: root.cx(4); y: root.cy(4) }
        PathLine { x: root.r; y: root.r }
    }

    ShapePath {
        strokeWidth: -1
        fillColor: root.shades[4]
        startX: root.r; startY: root.r
        PathLine { x: root.cx(4); y: root.cy(4) }
        PathLine { x: root.cx(5); y: root.cy(5) }
        PathLine { x: root.r; y: root.r }
    }

    ShapePath {
        strokeWidth: -1
        fillColor: root.shades[5]
        startX: root.r; startY: root.r
        PathLine { x: root.cx(5); y: root.cy(5) }
        PathLine { x: root.cx(6); y: root.cy(6) }
        PathLine { x: root.r; y: root.r }
    }
}
