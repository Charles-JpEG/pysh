"""Comprehensive tests for main.py functions to achieve 100% function coverage."""

import os
import sys
from pathlib import Path
from unittest import mock

import pytest  # type: ignore

# Add src directory to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from main import (
    is_posix_shell,
    find_posix_shell,
    get_default_shell,
    setup_readline,
    _set_indent_prefill,
    parse_args,
    main,
    POSIX_SHELLS
)


class TestIsPosixShell:
    """Test is_posix_shell function."""
    
    def test_bash_is_posix(self):
        """Test that bash is recognized as POSIX."""
        assert is_posix_shell("/bin/bash")
        assert is_posix_shell("/usr/bin/bash")
        assert is_posix_shell("bash")
    
    def test_zsh_is_posix(self):
        """Test that zsh is recognized as POSIX."""
        assert is_posix_shell("/usr/bin/zsh")
        assert is_posix_shell("zsh")
    
    def test_dash_is_posix(self):
        """Test that dash is recognized as POSIX."""
        assert is_posix_shell("/bin/dash")
    
    def test_fish_not_posix(self):
        """Test that fish is not POSIX."""
        assert not is_posix_shell("/usr/bin/fish")
        assert not is_posix_shell("fish")
    
    def test_empty_string_not_posix(self):
        """Test that empty string is not POSIX."""
        assert not is_posix_shell("")
    
    def test_unknown_shell_not_posix(self):
        """Test that unknown shells are not POSIX."""
        assert not is_posix_shell("/usr/bin/unknown_shell")
        assert not is_posix_shell("elvish")


class TestFindPosixShell:
    """Test find_posix_shell function."""
    
    def test_finds_available_posix_shell(self):
        """Test that it finds an available POSIX shell."""
        shell = find_posix_shell()
        # Should find at least one POSIX shell on the system
        assert shell is not None
        assert any(posix_name in shell for posix_name in POSIX_SHELLS)
    
    def test_returns_full_path(self):
        """Test that it returns a full path."""
        shell = find_posix_shell()
        if shell:
            assert os.path.isabs(shell)
    
    @mock.patch('shutil.which')
    def test_returns_none_if_no_shell_found(self, mock_which):
        """Test that it returns None if no POSIX shell is found."""
        mock_which.return_value = None
        shell = find_posix_shell()
        assert shell is None


class TestGetDefaultShell:
    """Test get_default_shell function."""
    
    def test_forced_posix_shell_no_warning(self):
        """Test that forcing a POSIX shell doesn't produce warning."""
        shell, warning = get_default_shell("/bin/bash")
        assert shell == "/bin/bash"
        assert not warning
    
    def test_forced_non_posix_shell_with_warning(self):
        """Test that forcing a non-POSIX shell produces warning."""
        shell, warning = get_default_shell("/usr/bin/fish")
        assert shell == "/usr/bin/fish"
        assert warning
    
    def test_auto_detect_posix_shell(self, monkeypatch):
        """Test auto-detection with POSIX shell in environment."""
        monkeypatch.setenv("SHELL", "/bin/bash")
        shell, warning = get_default_shell()
        assert shell == "/bin/bash"
        assert not warning
    
    def test_auto_detect_non_posix_finds_alternative(self, monkeypatch):
        """Test auto-detection with non-POSIX shell finds alternative."""
        monkeypatch.setenv("SHELL", "/usr/bin/fish")
        shell, warning = get_default_shell()
        # Should either use fish with warning or find alternative
        if shell == "/usr/bin/fish":
            assert warning
        else:
            assert is_posix_shell(shell)
            assert warning  # Still warns about original


class TestSetupReadline:
    """Test setup_readline function."""
    
    @pytest.mark.skipif(not sys.modules.get('readline'), reason="readline not available")
    def test_setup_readline_doesnt_crash(self):
        """Test that setup_readline doesn't crash when readline is available."""
        # Just make sure it doesn't crash
        try:
            setup_readline()
        except Exception as e:
            pytest.fail(f"setup_readline raised {e}")
    
    @mock.patch('main.readline', None)
    def test_setup_readline_handles_no_readline(self):
        """Test that setup_readline handles missing readline gracefully."""
        # Should not crash even if readline is None
        try:
            setup_readline()
        except Exception as e:
            pytest.fail(f"setup_readline raised {e} when readline is None")


class TestSetIndentPrefill:
    """Test _set_indent_prefill private function."""
    
    @pytest.mark.skipif(not sys.modules.get('readline'), reason="readline not available")
    def test_set_indent_prefill_with_indent(self):
        """Test setting indent prefill."""
        try:
            _set_indent_prefill("    ")
        except Exception as e:
            pytest.fail(f"_set_indent_prefill raised {e}")
    
    @pytest.mark.skipif(not sys.modules.get('readline'), reason="readline not available")
    def test_set_indent_prefill_empty(self):
        """Test setting empty indent prefill."""
        try:
            _set_indent_prefill("")
        except Exception as e:
            pytest.fail(f"_set_indent_prefill raised {e}")
    
    @mock.patch('main.readline', None)
    def test_set_indent_prefill_no_readline(self):
        """Test that _set_indent_prefill handles missing readline."""
        try:
            _set_indent_prefill("    ")
        except Exception as e:
            pytest.fail(f"_set_indent_prefill raised {e} when readline is None")


class TestParseArgs:
    """Test parse_args function (already covered but adding more)."""
    
    def test_parse_args_no_arguments(self):
        """Test parsing with no arguments."""
        args = parse_args([])
        assert args.shell is None
    
    def test_parse_args_long_shell_option(self):
        """Test parsing --shell option."""
        args = parse_args(["--shell", "/bin/bash"])
        assert args.shell == "/bin/bash"
    
    def test_parse_args_short_shell_option(self):
        """Test parsing -s option."""
        args = parse_args(["-s", "/usr/bin/zsh"])
        assert args.shell == "/usr/bin/zsh"
    
    def test_parse_args_help(self):
        """Test that --help exits."""
        with pytest.raises(SystemExit):
            parse_args(["--help"])


class TestMainFunction:
    """Test main function."""
    
    def test_main_with_shell_option(self, monkeypatch):
        """Test main with shell option."""
        # Mock sys.argv
        monkeypatch.setattr('sys.argv', ['pysh', '--shell', '/bin/bash'])
        
        # Mock input() to simulate EOF
        def mock_input(prompt):
            raise EOFError()
        monkeypatch.setattr('builtins.input', mock_input)
        
        # Should not crash
        try:
            main()
        except (SystemExit, EOFError):
            pass  # Expected
    
    def test_main_default(self, monkeypatch):
        """Test main with default arguments."""
        # Mock sys.argv
        monkeypatch.setattr('sys.argv', ['pysh'])
        
        # Mock input() to simulate EOF
        def mock_input(prompt):
            raise EOFError()
        monkeypatch.setattr('builtins.input', mock_input)
        
        # Should not crash
        try:
            main()
        except (SystemExit, EOFError):
            pass  # Expected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
