class Navi < Formula
  include Language::Python::Virtualenv

  desc "Voice notes that just work - hotkey capture with local Whisper transcription"
  homepage "https://github.com/angad729/navi"
  url "https://files.pythonhosted.org/packages/source/n/navi-voice/navi-voice-0.1.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"  # Update after PyPI release
  license "MIT"

  depends_on "python@3.11"
  depends_on :macos

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      To get started:
        1. Install Ollama: brew install ollama
        2. Pull the model: ollama pull llama3.2
        3. Run setup: navi setup
        4. Start Navi: navi start

      Grant microphone and accessibility permissions when prompted.
    EOS
  end

  test do
    assert_match "navi", shell_output("#{bin}/navi --version")
  end
end
