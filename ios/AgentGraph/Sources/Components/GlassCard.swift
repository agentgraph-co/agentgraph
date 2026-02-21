// GlassCard — Frosted glass container matching web .glass class
// iOS 18: Material + tint overlay
// iOS 26+: Native Liquid Glass (progressive enhancement)

import SwiftUI

// MARK: - Glass Card Modifier (iOS 18+)

struct GlassCardModifier: ViewModifier {
    var padding: CGFloat = AGSpacing.xl
    var cornerRadius: CGFloat = AGRadii.xl

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(.ultraThinMaterial)
            .background(Color.agSurface.opacity(0.5))
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(Color.white.opacity(0.06), lineWidth: 1)
            )
            .shadow(color: .black.opacity(0.3), radius: 8, y: 4)
    }
}

extension View {
    func glassCard(
        padding: CGFloat = AGSpacing.xl,
        cornerRadius: CGFloat = AGRadii.xl
    ) -> some View {
        modifier(GlassCardModifier(padding: padding, cornerRadius: cornerRadius))
    }
}

// MARK: - Glass Card Container

struct GlassCard<Content: View>: View {
    let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        content.glassCard()
    }
}
