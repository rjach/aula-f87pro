// System audio level meter for the `pulse` theme.
//
// Captures everything the Mac is playing through ScreenCaptureKit (macOS 13+),
// splits it into frequency bands, and prints one line per ~16 ms window:
//
//     <loudness> <band 0> <band 1> ... <band N-1>
//
// Every value is an RMS amplitude (0.0 = silence, ~0.7 = a full-scale sine).
// Bands run from bass to treble. Nothing is recorded or stored: each window is
// reduced to these numbers and the samples are dropped.
//
// Python compiles this once with `swiftc` and reads its stdout. Errors go to
// stderr as a single line starting with "error:".

import AVFoundation
import CoreMedia
import Foundation
import ScreenCaptureKit

/// Band centre frequencies in Hz, roughly log-spaced from sub-bass to air.
let bandCenters: [Double] = [45, 80, 140, 250, 420, 700, 1150, 1900, 3100, 5000, 8000, 12000]
/// Bandwidth of each band filter. ~1.4 keeps neighbouring bands distinct
/// without leaving gaps between them.
let bandQuality = 1.4
/// Seconds of audio per printed line. ~60 lines a second keeps beats tight.
let windowSeconds = 1.0 / 60.0

/// One RBJ band-pass biquad (constant 0 dB peak gain).
struct BandPass {
    var b0 = 0.0, b2 = 0.0, a1 = 0.0, a2 = 0.0
    var x1 = 0.0, x2 = 0.0, y1 = 0.0, y2 = 0.0

    init(center: Double, quality: Double, sampleRate: Double) {
        let omega = 2 * Double.pi * min(center, sampleRate * 0.45) / sampleRate
        let alpha = sin(omega) / (2 * quality)
        let a0 = 1 + alpha
        b0 = alpha / a0
        b2 = -alpha / a0
        a1 = -2 * cos(omega) / a0
        a2 = (1 - alpha) / a0
    }

    mutating func process(_ x: Double) -> Double {
        let y = b0 * x + b2 * x2 - a1 * y1 - a2 * y2
        x2 = x1; x1 = x
        y2 = y1; y1 = y
        return y
    }
}

/// Turns raw samples into windowed band levels and prints them.
final class LevelMeter {
    private var sampleRate = 0.0
    private var filters: [BandPass] = []
    private var bandSums: [Double] = []
    private var totalSum = 0.0
    private var count = 0
    private var windowLength = 0

    private func configure(sampleRate rate: Double) {
        sampleRate = rate
        filters = bandCenters.map { BandPass(center: $0, quality: bandQuality, sampleRate: rate) }
        bandSums = Array(repeating: 0, count: bandCenters.count)
        windowLength = max(64, Int(rate * windowSeconds))
        count = 0
        totalSum = 0
    }

    func consume(_ sampleBuffer: CMSampleBuffer) {
        guard let format = sampleBuffer.formatDescription?.audioStreamBasicDescription else { return }
        if format.mSampleRate != sampleRate { configure(sampleRate: format.mSampleRate) }
        guard format.mFormatFlags & kAudioFormatFlagIsFloat != 0 else { return }

        try? sampleBuffer.withAudioBufferList { bufferList, _ in
            let channels = bufferList.map { buffer -> UnsafeBufferPointer<Float> in
                let frames = Int(buffer.mDataByteSize) / MemoryLayout<Float>.size
                return UnsafeBufferPointer(start: buffer.mData?.assumingMemoryBound(to: Float.self),
                                           count: frames)
            }
            guard let first = channels.first, !first.isEmpty else { return }
            let isInterleaved = format.mFormatFlags & kAudioFormatFlagIsNonInterleaved == 0
            let channelCount = isInterleaved ? Int(format.mChannelsPerFrame) : channels.count
            let frameCount = isInterleaved ? first.count / max(1, channelCount) : first.count

            for frame in 0..<frameCount {
                var mono = 0.0
                if isInterleaved {
                    for channel in 0..<channelCount { mono += Double(first[frame * channelCount + channel]) }
                } else {
                    for channel in channels { mono += Double(channel[frame]) }
                }
                mono /= Double(max(1, channelCount))
                add(mono)
            }
        }
    }

    /// Feed a synthetic tone instead of captured audio. Used by
    /// `--tone <hz>` to check the band split without any permission.
    func consumeTone(frequency: Double, seconds: Double, sampleRate rate: Double = 48_000) {
        configure(sampleRate: rate)
        for index in 0..<Int(seconds * rate) {
            add(0.5 * sin(2 * Double.pi * frequency * Double(index) / rate))
        }
    }

    private func add(_ sample: Double) {
        totalSum += sample * sample
        for index in filters.indices {
            let filtered = filters[index].process(sample)
            bandSums[index] += filtered * filtered
        }
        count += 1
        if count >= windowLength { emit() }
    }

    private func emit() {
        let scale = 1.0 / Double(count)
        var line = String(format: "%.5f", (totalSum * scale).squareRoot())
        for sum in bandSums { line += String(format: " %.5f", (sum * scale).squareRoot()) }
        line += "\n"
        FileHandle.standardOutput.write(line.data(using: .utf8)!)
        for index in bandSums.indices { bandSums[index] = 0 }
        totalSum = 0
        count = 0
    }
}

final class Capture: NSObject, SCStreamOutput, SCStreamDelegate {
    let meter = LevelMeter()
    var stream: SCStream?

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer,
                of type: SCStreamOutputType) {
        // Video frames are requested only because a stream needs a display;
        // they are tiny, rare and ignored.
        guard type == .audio else { return }
        meter.consume(sampleBuffer)
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        fail("capture stopped: \(error.localizedDescription)")
    }
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write("error: \(message)\n".data(using: .utf8)!)
    exit(1)
}

let arguments = CommandLine.arguments
if let flag = arguments.firstIndex(of: "--tone"), flag + 1 < arguments.count,
   let frequency = Double(arguments[flag + 1]) {
    LevelMeter().consumeTone(frequency: frequency, seconds: 0.25)
    exit(0)
}

let capture = Capture()
let parentProcess = getppid()

SCShareableContent.getExcludingDesktopWindows(false, onScreenWindowsOnly: true) { content, error in
    if let error = error {
        fail("no permission to capture system audio (\(error.localizedDescription)). "
             + "Allow your terminal under System Settings > Privacy & Security > "
             + "Screen & System Audio Recording, then restart the terminal.")
    }
    guard let display = content?.displays.first else { fail("no display found to attach the audio capture to") }

    let configuration = SCStreamConfiguration()
    configuration.capturesAudio = true
    configuration.excludesCurrentProcessAudio = true
    configuration.sampleRate = 48_000
    configuration.channelCount = 2
    // The smallest, slowest video a stream accepts: audio is all we want.
    configuration.width = 2
    configuration.height = 2
    configuration.minimumFrameInterval = CMTime(value: 1, timescale: 1)
    configuration.queueDepth = 1

    let filter = SCContentFilter(display: display, excludingWindows: [])
    let stream = SCStream(filter: filter, configuration: configuration, delegate: capture)
    capture.stream = stream
    do {
        let queue = DispatchQueue(label: "aula.audio")
        try stream.addStreamOutput(capture, type: .audio, sampleHandlerQueue: queue)
        try stream.addStreamOutput(capture, type: .screen, sampleHandlerQueue: queue)
    } catch {
        fail("could not attach to the audio stream: \(error.localizedDescription)")
    }
    stream.startCapture { error in
        if let error = error { fail("could not start capture: \(error.localizedDescription)") }
    }
}

// Exit with the lighting process rather than lingering as an orphan.
Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { _ in
    if getppid() != parentProcess { exit(0) }
}

RunLoop.main.run()
