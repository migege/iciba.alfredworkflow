import Foundation
import NaturalLanguage
import Translation

private struct Input: Decodable {
    let text: String
    let source: String?
    let target: String?
    let checkOnly: Bool?
}

private struct Output: Encodable {
    let status: String
    var translation: String = ""
    var source: String = ""
    var target: String = ""
    var message: String = ""
}

@main
struct AppleTranslate {
    private static func emit(_ output: Output) {
        if let data = try? JSONEncoder().encode(output) {
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data([10]))
        }
    }

    static func main() async {
        do {
            let input = try JSONDecoder().decode(
                Input.self, from: FileHandle.standardInput.readDataToEndOfFile())
            let text = input.text.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !text.isEmpty else {
                emit(Output(status: "error", message: "没有可翻译的文本"))
                return
            }
            let recognizer = NLLanguageRecognizer()
            recognizer.processString(text)
            guard let sourceID = input.source ?? recognizer.dominantLanguage?.rawValue else {
                emit(Output(status: "error", message: "无法识别语言，请设置 translation_source"))
                return
            }
            let targetID = input.target ?? (sourceID.hasPrefix("zh") ? "en" : "zh-Hans")
            let source = Locale.Language(identifier: sourceID)
            let target = Locale.Language(identifier: targetID)
            let availability: LanguageAvailability
            let session: TranslationSession
            if #available(macOS 26.4, *) {
                availability = LanguageAvailability(preferredStrategy: .highFidelity)
                session = TranslationSession(
                    installedSource: source, target: target, preferredStrategy: .highFidelity)
            } else {
                availability = LanguageAvailability()
                session = TranslationSession(installedSource: source, target: target)
            }
            let status = await availability.status(from: source, to: target)
            switch status {
            case .installed:
                if input.checkOnly == true {
                    emit(Output(status: "installed", source: sourceID, target: targetID))
                    return
                }
                let response = try await session.translate(text)
                emit(Output(status: "translated", translation: response.targetText,
                            source: sourceID, target: targetID))
            case .supported:
                emit(Output(status: "not_installed", source: sourceID, target: targetID,
                            message: "请在系统设置 → 通用 → 语言与地区 → 翻译语言中下载所需语言"))
            case .unsupported:
                emit(Output(status: "unsupported", source: sourceID, target: targetID,
                            message: "Apple 翻译不支持此语言组合"))
            @unknown default:
                emit(Output(status: "error", message: "无法检查翻译语言"))
            }
        } catch TranslationError.notInstalled {
            emit(Output(status: "not_installed",
                        message: "请在系统设置 → 通用 → 语言与地区 → 翻译语言中下载所需语言"))
        } catch {
            // Avoid logging the user's text or any raw system diagnostics to Alfred's XML stream.
            emit(Output(status: "error", message: "Apple 本地翻译暂不可用"))
        }
    }
}
