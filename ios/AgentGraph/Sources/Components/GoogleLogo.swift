// GoogleLogo — Official Google "G" multicolor logo as SwiftUI view

import SwiftUI

struct GoogleLogo: View {
    var body: some View {
        Canvas { context, size in
            let scale = min(size.width, size.height) / 18

            // Blue path
            var blue = Path()
            blue.addLines([
                CGPoint(x: 17.64 * scale, y: 9.2 * scale),
            ])
            blue.move(to: CGPoint(x: 17.64 * scale, y: 9.2 * scale))
            blue.addQuadCurve(
                to: CGPoint(x: 17.476 * scale, y: 7.36 * scale),
                control: CGPoint(x: 17.64 * scale, y: 8.563 * scale)
            )
            blue.addLine(to: CGPoint(x: 9 * scale, y: 7.36 * scale))
            blue.addLine(to: CGPoint(x: 9 * scale, y: 10.841 * scale))
            blue.addLine(to: CGPoint(x: 13.844 * scale, y: 10.841 * scale))
            blue.addQuadCurve(
                to: CGPoint(x: 12.048 * scale, y: 13.557 * scale),
                control: CGPoint(x: 13.444 * scale, y: 12.241 * scale)
            )
            blue.addLine(to: CGPoint(x: 14.956 * scale, y: 15.816 * scale))
            blue.addQuadCurve(
                to: CGPoint(x: 17.64 * scale, y: 9.2 * scale),
                control: CGPoint(x: 16.658 * scale, y: 14.249 * scale)
            )
            blue.closeSubpath()
            context.fill(blue, with: .color(Color(red: 66/255, green: 133/255, blue: 244/255)))

            // Green path
            var green = Path()
            green.move(to: CGPoint(x: 9 * scale, y: 18 * scale))
            green.addQuadCurve(
                to: CGPoint(x: 14.956 * scale, y: 15.82 * scale),
                control: CGPoint(x: 11.43 * scale, y: 18 * scale)
            )
            green.addLine(to: CGPoint(x: 12.048 * scale, y: 13.561 * scale))
            green.addQuadCurve(
                to: CGPoint(x: 9 * scale, y: 14.421 * scale),
                control: CGPoint(x: 11.242 * scale, y: 14.101 * scale)
            )
            green.addQuadCurve(
                to: CGPoint(x: 3.964 * scale, y: 10.71 * scale),
                control: CGPoint(x: 6.656 * scale, y: 14.421 * scale)
            )
            green.addLine(to: CGPoint(x: 0.957 * scale, y: 13.042 * scale))
            green.addQuadCurve(
                to: CGPoint(x: 9 * scale, y: 18 * scale),
                control: CGPoint(x: 3.485 * scale, y: 16.35 * scale)
            )
            green.closeSubpath()
            context.fill(green, with: .color(Color(red: 52/255, green: 168/255, blue: 83/255)))

            // Yellow path
            var yellow = Path()
            yellow.move(to: CGPoint(x: 3.964 * scale, y: 10.71 * scale))
            yellow.addQuadCurve(
                to: CGPoint(x: 3.682 * scale, y: 9 * scale),
                control: CGPoint(x: 3.782 * scale, y: 10.117 * scale)
            )
            yellow.addQuadCurve(
                to: CGPoint(x: 3.964 * scale, y: 7.29 * scale),
                control: CGPoint(x: 3.682 * scale, y: 8.407 * scale)
            )
            yellow.addLine(to: CGPoint(x: 0.957 * scale, y: 4.958 * scale))
            yellow.addQuadCurve(
                to: CGPoint(x: 0 * scale, y: 9 * scale),
                control: CGPoint(x: 0.348 * scale, y: 6.173 * scale)
            )
            yellow.addQuadCurve(
                to: CGPoint(x: 0.957 * scale, y: 13.042 * scale),
                control: CGPoint(x: 0 * scale, y: 10.452 * scale)
            )
            yellow.addLine(to: CGPoint(x: 3.964 * scale, y: 10.71 * scale))
            yellow.closeSubpath()
            context.fill(yellow, with: .color(Color(red: 251/255, green: 188/255, blue: 5/255)))

            // Red path
            var red = Path()
            red.move(to: CGPoint(x: 9 * scale, y: 3.58 * scale))
            red.addQuadCurve(
                to: CGPoint(x: 12.44 * scale, y: 4.925 * scale),
                control: CGPoint(x: 10.321 * scale, y: 3.58 * scale)
            )
            red.addLine(to: CGPoint(x: 15.022 * scale, y: 2.345 * scale))
            red.addQuadCurve(
                to: CGPoint(x: 9 * scale, y: 0 * scale),
                control: CGPoint(x: 13.463 * scale, y: 0.891 * scale)
            )
            red.addQuadCurve(
                to: CGPoint(x: 0.957 * scale, y: 4.958 * scale),
                control: CGPoint(x: 4.046 * scale, y: 0 * scale)
            )
            red.addLine(to: CGPoint(x: 3.964 * scale, y: 7.29 * scale))
            red.addQuadCurve(
                to: CGPoint(x: 9 * scale, y: 3.58 * scale),
                control: CGPoint(x: 4.672 * scale, y: 5.163 * scale)
            )
            red.closeSubpath()
            context.fill(red, with: .color(Color(red: 234/255, green: 67/255, blue: 53/255)))
        }
    }
}
