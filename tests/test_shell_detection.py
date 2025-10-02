import os
import sys
import subprocess
import tempfile
from pathlib import Path

import pytest  # type: ignore

# Add src directory to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from main import get_default_shell, is_posix_shell, POSIX_SHELLS, parse_args


class TestShellDetection:
    """Test shell detection and POSIX compliance checking."""
    
    def test_posix_shell_detection(self):
        """Test that known POSIX shells are correctly identified."""
        # Test known POSIX shells
        assert is_posix_shell("/bin/bash")
        assert is_posix_shell("/usr/bin/zsh")
        assert is_posix_shell("sh")
        assert is_posix_shell("/usr/local/bin/dash")
        
        # Test non-POSIX shells
        assert not is_posix_shell("/usr/bin/fish")
        assert not is_posix_shell("/usr/bin/csh")
        assert not is_posix_shell("/usr/bin/tcsh")
        assert not is_posix_shell("elvish")
        
        # Test edge cases
        assert not is_posix_shell("")
        assert not is_posix_shell("/nonexistent/shell")
    
    def test_posix_shells_list_completeness(self):
        """Test that the POSIX shells list contains expected shells."""
        expected_shells = ["bash", "zsh", "dash", "sh", "ksh", "mksh", "pdksh", "ash"]
        for shell in expected_shells:
            assert shell in POSIX_SHELLS, f"Expected shell '{shell}' not in POSIX_SHELLS"
    
    def test_default_shell_with_posix_shell(self):
        """Test shell selection when current shell is POSIX-compliant."""
        # Test with a POSIX shell
        shell, warning = get_default_shell("/bin/bash")
        assert shell == "/bin/bash"
        assert not warning
        
        shell, warning = get_default_shell("/usr/bin/zsh")
        assert shell == "/usr/bin/zsh"
        assert not warning
    
    def test_default_shell_with_non_posix_shell(self):
        """Test shell selection when forced shell is non-POSIX."""
        # Test with a non-POSIX shell - should still use it but warn
        shell, warning = get_default_shell("/usr/bin/fish")
        assert shell == "/usr/bin/fish"
        assert warning
    
    def test_default_shell_auto_selection(self, monkeypatch):
        """Test automatic shell selection from environment."""
        # Test with POSIX shell in SHELL env var
        monkeypatch.setenv("SHELL", "/bin/bash")
        shell, warning = get_default_shell()
        assert shell == "/bin/bash"
        assert not warning
        
        # Test with non-POSIX shell in SHELL env var
        # This should try to find a POSIX alternative
        monkeypatch.setenv("SHELL", "/usr/bin/fish")
        shell, warning = get_default_shell()
        # Should either find a POSIX shell or warn about fish
        if shell == "/usr/bin/fish":
            assert warning  # Warning issued for non-POSIX
        else:
            assert is_posix_shell(shell)  # Found POSIX alternative
            assert warning  # Still warned about original non-POSIX
    
    def test_shell_fallback_behavior(self, monkeypatch):
        """Test shell fallback when SHELL is not set."""
        # Remove SHELL env var
        monkeypatch.delenv("SHELL", raising=False)
        
        # Should fall back to login shell or POSIX shell
        shell, warning = get_default_shell()
        assert shell  # Should get some shell
        assert shell.endswith(("sh", "bash", "zsh", "dash", "ksh", "ash"))


class TestCommandLineOptions:
    """Test command-line argument parsing."""
    
    def test_help_option(self):
        """Test that help option works."""
        with pytest.raises(SystemExit):
            parse_args(["--help"])
    
    def test_shell_option_long(self):
        """Test --shell option."""
        args = parse_args(["--shell", "/bin/bash"])
        assert args.shell == "/bin/bash"
    
    def test_shell_option_short(self):
        """Test -s option."""
        args = parse_args(["-s", "/usr/bin/zsh"])
        assert args.shell == "/usr/bin/zsh"
    
    def test_no_options(self):
        """Test default behavior with no options."""
        args = parse_args([])
        assert args.shell is None


class TestPyshIntegration:
    """Integration tests for pysh with different shell options."""
    
    def get_pysh_path(self):
        """Get path to pysh main.py."""
        return Path(__file__).parent.parent / "src" / "main.py"
    
    def test_pysh_with_posix_shell(self):
        """Test pysh runs without warnings with POSIX shell."""
        pysh_path = self.get_pysh_path()
        
        # Test with bash
        result = subprocess.run(
            [sys.executable, str(pysh_path), "--shell", "/bin/bash"],
            input="echo 'test'\n",
            text=True,
            capture_output=True,
            timeout=5
        )
        
        assert result.returncode == 0
        assert "test" in result.stdout
        # Should not have warnings for POSIX shell
        assert "Warning:" not in result.stderr
    
    def test_pysh_with_non_posix_shell(self):
        """Test pysh shows warning with non-POSIX shell."""
        pysh_path = self.get_pysh_path()
        
        # Test with fish (if available)
        fish_path = "/usr/bin/fish"
        if not Path(fish_path).exists():
            pytest.skip("Fish shell not available for testing")
        
        result = subprocess.run(
            [sys.executable, str(pysh_path), "--shell", fish_path],
            input="echo 'test'\n",
            text=True,
            capture_output=True,
            timeout=5
        )
        
        assert result.returncode == 0
        assert "test" in result.stdout
        # Should have warning for non-POSIX shell
        assert "Warning:" in result.stderr
        assert "may not be POSIX-compliant" in result.stderr
    
    def test_pysh_hybrid_functionality(self):
        """Test that hybrid Python/shell functionality works with shell options."""
        pysh_path = self.get_pysh_path()
        
        # Test hybrid for loop with shell commands
        input_script = "for i in range(3):\n    echo $i\n\n"
        
        result = subprocess.run(
            [sys.executable, str(pysh_path), "-s", "/bin/bash"],
            input=input_script,
            text=True,
            capture_output=True,
            timeout=5
        )
        
        assert result.returncode == 0
        # Should print 0, 1, 2
        output_lines = [line.strip() for line in result.stdout.split('\n') if line.strip()]
        assert "0" in result.stdout
        assert "1" in result.stdout
        assert "2" in result.stdout
    
    def test_pysh_auto_posix_selection(self, monkeypatch):
        """Test automatic POSIX shell selection when SHELL is non-POSIX."""
        pysh_path = self.get_pysh_path()
        
        # Set SHELL to fish and test auto-selection
        env = os.environ.copy()
        env["SHELL"] = "/usr/bin/fish"
        
        result = subprocess.run(
            [sys.executable, str(pysh_path)],
            input="echo 'auto selection test'\n",
            text=True,
            capture_output=True,
            env=env,
            timeout=5
        )
        
        assert result.returncode == 0
        assert "auto selection test" in result.stdout
        
        # Should either warn about fish or use alternative
        if "/usr/bin/fish" in result.stderr:
            assert "Warning:" in result.stderr
        # The system should still work regardless


if __name__ == "__main__":
    pytest.main([__file__])