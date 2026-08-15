import AppKit
import Foundation
import PDFKit

guard CommandLine.arguments.count >= 4 else {
    FileHandle.standardError.write(Data("usage: render_pdf_pages.swift INPUT.pdf OUTPUT_DIR PAGE...\n".utf8))
    exit(2)
}

let inputURL = URL(fileURLWithPath: CommandLine.arguments[1])
let outputDirectory = URL(fileURLWithPath: CommandLine.arguments[2], isDirectory: true)
guard let document = PDFDocument(url: inputURL) else {
    FileHandle.standardError.write(Data("unable to open PDF\n".utf8))
    exit(3)
}

try FileManager.default.createDirectory(at: outputDirectory, withIntermediateDirectories: true)

for value in CommandLine.arguments.dropFirst(3) {
    guard let pageNumber = Int(value), pageNumber > 0,
          let page = document.page(at: pageNumber - 1) else {
        continue
    }
    let bounds = page.bounds(for: .mediaBox)
    let scale = 150.0 / 72.0
    let size = NSSize(width: max(1, bounds.width * scale), height: max(1, bounds.height * scale))
    let image = page.thumbnail(of: size, for: .mediaBox)
    guard let tiff = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let png = bitmap.representation(using: .png, properties: [:]) else {
        continue
    }
    let filename = String(format: "page_%02d.png", pageNumber)
    try png.write(to: outputDirectory.appendingPathComponent(filename))
}
