// AgentGraph Design System — SwiftUI Theme
// Extended from design-system/ios/AgentGraphTheme.swift
// Source of truth: design-system/tokens.json

import SwiftUI

// MARK: - Colors (Dark — default)

extension Color {
    static let agPrimary = Color(red: 0.388, green: 0.400, blue: 0.945)       // #6366F1
    static let agPrimaryDark = Color(red: 0.310, green: 0.275, blue: 0.898)    // #4F46E5
    static let agPrimaryLight = Color(red: 0.506, green: 0.549, blue: 0.973)   // #818CF8
    static let agSurface = Color(red: 0.118, green: 0.118, blue: 0.180)        // #1E1E2E
    static let agSurfaceHover = Color(red: 0.165, green: 0.165, blue: 0.243)   // #2A2A3E
    static let agSurfaceElevated = Color(red: 0.145, green: 0.145, blue: 0.220) // #252538
    static let agBackground = Color(red: 0.067, green: 0.067, blue: 0.106)     // #11111B
    static let agText = Color(red: 0.804, green: 0.839, blue: 0.957)           // #CDD6F4
    static let agMuted = Color(red: 0.424, green: 0.439, blue: 0.525)          // #6C7086
    static let agBorder = Color(red: 0.192, green: 0.196, blue: 0.267)         // #313244
    static let agSuccess = Color(red: 0.651, green: 0.890, blue: 0.631)        // #A6E3A1
    static let agWarning = Color(red: 0.976, green: 0.886, blue: 0.686)        // #F9E2AF
    static let agDanger = Color(red: 0.953, green: 0.545, blue: 0.659)         // #F38BA8
    static let agAccent = Color(red: 0.537, green: 0.706, blue: 0.980)         // #89B4FA
}

// MARK: - Light Mode Colors

extension Color {
    static let agSurfaceLight = Color(red: 1.0, green: 1.0, blue: 1.0)           // #FFFFFF
    static let agSurfaceHoverLight = Color(red: 0.945, green: 0.961, blue: 0.976) // #F1F5F9
    static let agBackgroundLight = Color(red: 0.973, green: 0.980, blue: 0.988)   // #F8FAFC
    static let agTextLight = Color(red: 0.118, green: 0.161, blue: 0.231)         // #1E293B
    static let agMutedLight = Color(red: 0.392, green: 0.455, blue: 0.545)        // #64748B
    static let agBorderLight = Color(red: 0.886, green: 0.910, blue: 0.941)       // #E2E8F0
    static let agSuccessLight = Color(red: 0.086, green: 0.639, blue: 0.290)      // #16A34A
    static let agWarningLight = Color(red: 0.792, green: 0.541, blue: 0.016)      // #CA8A04
    static let agDangerLight = Color(red: 0.863, green: 0.149, blue: 0.149)       // #DC2626
    static let agAccentLight = Color(red: 0.145, green: 0.388, blue: 0.922)       // #2563EB
}

// MARK: - Typography (System fonts — no bundled Inter)

struct AGTypography {
    static let xs: Font = .system(size: 12)
    static let sm: Font = .system(size: 14)
    static let base: Font = .system(size: 16)
    static let lg: Font = .system(size: 18)
    static let xl: Font = .system(size: 20)
    static let xxl: Font = .system(size: 24, weight: .semibold)
    static let xxxl: Font = .system(size: 30, weight: .bold)
    static let display: Font = .system(size: 36, weight: .bold)
    static let hero: Font = .system(size: 48, weight: .bold)
}

// MARK: - Spacing

struct AGSpacing {
    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 12
    static let base: CGFloat = 16
    static let lg: CGFloat = 20
    static let xl: CGFloat = 24
    static let xxl: CGFloat = 32
    static let xxxl: CGFloat = 48
    static let huge: CGFloat = 64
}

// MARK: - Corner Radii

struct AGRadii {
    static let sm: CGFloat = 4
    static let md: CGFloat = 6
    static let lg: CGFloat = 8
    static let xl: CGFloat = 12
    static let xxl: CGFloat = 16
    static let full: CGFloat = 9999
}

// MARK: - Shadows

extension View {
    func agShadowSm() -> some View {
        self.shadow(color: .black.opacity(0.3), radius: 2, x: 0, y: 1)
    }

    func agShadowMd() -> some View {
        self.shadow(color: .black.opacity(0.3), radius: 6, x: 0, y: 4)
    }

    func agShadowLg() -> some View {
        self.shadow(color: .black.opacity(0.3), radius: 30, x: 0, y: 8)
    }

    func agGlowPrimary() -> some View {
        self.shadow(color: .agPrimary.opacity(0.5), radius: 20, x: 0, y: 0)
    }

    func agGlowAccent() -> some View {
        self.shadow(color: .agAccent.opacity(0.4), radius: 20, x: 0, y: 0)
    }
}

// MARK: - Gradients

struct AGGradients {
    static let primary = LinearGradient(
        colors: [.agPrimaryLight, .agAccent],
        startPoint: .leading,
        endPoint: .trailing
    )

    static let primaryVertical = LinearGradient(
        colors: [.agPrimary, .agPrimaryDark],
        startPoint: .top,
        endPoint: .bottom
    )

    static let surfaceFade = LinearGradient(
        colors: [.agBackground, .agBackground.opacity(0)],
        startPoint: .bottom,
        endPoint: .top
    )
}

extension View {
    func gradientForeground() -> some View {
        self.overlay(AGGradients.primary)
            .mask(self)
    }
}

// MARK: - Liquid Glass (iOS 26+)

@available(iOS 26.0, *)
extension View {
    func agGlassEffect() -> some View {
        self.glassEffect(.regular.tint(.agPrimary))
    }

    func agGlassSubtle() -> some View {
        self.glassEffect(.regular)
    }
}
