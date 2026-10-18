import AppKit
import Foundation

// Generates exact-logo flat social cards with no external packages.
// Run on macOS: swift assets/branding/generate-social-preview.swift
let root = URL(fileURLWithPath: FileManager.default.currentDirectoryPath, isDirectory: true)
let assets = root.appendingPathComponent("assets/branding", isDirectory: true)

func color(_ rgb: UInt32) -> NSColor {
    return NSColor(calibratedRed: CGFloat((rgb >> 16) & 0xff) / 255.0,
                   green: CGFloat((rgb >> 8) & 0xff) / 255.0,
                   blue: CGFloat(rgb & 0xff) / 255.0, alpha: 1.0)
}
func round(_ rect: NSRect, _ radius: CGFloat, _ c: NSColor) {
    c.setFill()
    NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius).fill()
}
func stroke(_ rect: NSRect, _ radius: CGFloat, _ c: NSColor, _ width: CGFloat = 1.0) {
    let p = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    p.lineWidth = width
    c.setStroke()
    p.stroke()
}
func line(_ points: [NSPoint], _ c: NSColor, _ width: CGFloat = 1.0) {
    let p = NSBezierPath()
    if let first = points.first {
        p.move(to: first)
        for x in points.dropFirst() { p.line(to: x) }
    }
    p.lineWidth = width
    c.setStroke()
    p.stroke()
}
func centered(_ string: String, y: CGFloat, font: NSFont, foreground: NSColor) {
    let attributes: [NSAttributedString.Key: Any] = [
        .font: font, .foregroundColor: foreground,
        .kern: 0.1
    ]
    let sized = (string as NSString).size(withAttributes: attributes)
    (string as NSString).draw(at: NSPoint(x: (1280 - sized.width)/2, y: y), withAttributes: attributes)
}

for theme in ["dark","light"] {
    let dark = theme == "dark"
    let background = dark ? color(0x090F19) : color(0xFFFFFF)
    let outline = dark ? color(0x263951) : color(0xD4DFEC)
    let primary = dark ? color(0xFFFFFF) : color(0x142338)
    let secondary = dark ? color(0xBED0E2) : color(0x4A6078)
    let quiet = dark ? color(0x8EA2B7) : color(0x546983)
    let blue = color(0x176FFF)
    let logoURL = assets.appendingPathComponent("tuckbit-logo-\(theme).png")
    let image = NSImage(contentsOf: logoURL)
    guard let logo = image else { fatalError("Missing branded logo: \(logoURL.path)") }
    guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1280, pixelsHigh: 640,
                                       bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
                                       isPlanar: false, colorSpaceName: .deviceRGB,
                                       bytesPerRow: 0, bitsPerPixel: 0) else {
        fatalError("Could not allocate social preview")
    }
    guard let context = NSGraphicsContext(bitmapImageRep: bitmap) else {
        fatalError("Could not create bitmap context")
    }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    context.imageInterpolation = .high

    background.setFill()
    NSRect(x:0,y:0,width:1280,height:640).fill()
    stroke(NSRect(x:20,y:20,width:1240,height:600),24,outline)
    // Restrained editorial motif: routing line and two blue nodes, not a decorative gradient.
    line([NSPoint(x:95,y:545),NSPoint(x:1178,y:545)],outline,1)
    round(NSRect(x:94,y:542,width:26,height:5),2,blue)
    round(NSRect(x:1167,y:542,width:11,height:5),2,blue)

    centered("OPEN SOURCE  /  AI CODING AGENTS",y:567,
             font:NSFont.monospacedSystemFont(ofSize:17, weight:.medium),foreground:quiet)
    // Use the exact existing themed wordmark artwork. Do not redraw brand geometry.
    logo.draw(in:NSRect(x:185,y:229,width:910,height:303),from:.zero,
              operation:.sourceOver,fraction:1,respectFlipped:false,hints:nil)
    centered("Every tool. Right on cue.",y:175,
             font:NSFont.systemFont(ofSize:39,weight:.semibold),foreground:primary)
    centered("SCOPED CONTEXT     ·     RELEVANT TOOLS     ·     REQUIRED CHECKS",y:118,
             font:NSFont.systemFont(ofSize:19,weight:.medium),foreground:secondary)
    line([NSPoint(x:95,y:91),NSPoint(x:1180,y:91)],outline,1)
    centered("github.com/MakeItEzzz555/tuck-bit",y:50,
             font:NSFont.monospacedSystemFont(ofSize:17,weight:.medium),foreground:quiet)

    NSGraphicsContext.restoreGraphicsState()

    guard let png = bitmap.representation(using:.png,properties:[:]) else {fatalError("PNG export failed") }
    let output = assets.appendingPathComponent("tuckbit-social-preview-\(theme).png")
    try png.write(to:output,options:.atomic)
    print("Created \(output.path) (\(png.count) bytes, 1280x640)")
}
