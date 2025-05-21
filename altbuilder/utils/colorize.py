import colorama
from colorama import Fore, Style

colorama.init()


def colorize(text, color=None, bold=False):
    """Colorize text using ANSI escape codes with flexible color names.

    Args:
        text (str): The text to colorize.
        color (str, optional): Color name (e.g., 'red', 'blue', 'purple'). Case-insensitive.
        bold (bool, optional): If True, applies bold formatting. Defaults to False.

    Returns:
        str: The colorized text with ANSI escape codes.
    """
    # Map common color names to colorama Fore attributes
    color_map = {
        "black": Fore.BLACK,
        "red": Fore.RED,
        "green": Fore.GREEN,
        "yellow": Fore.YELLOW,
        "blue": Fore.BLUE,
        "magenta": Fore.MAGENTA,
        "cyan": Fore.CYAN,
        "white": Fore.WHITE,
        "lightblack": Fore.LIGHTBLACK_EX,
        "lightred": Fore.LIGHTRED_EX,
        "lightgreen": Fore.LIGHTGREEN_EX,
        "lightyellow": Fore.LIGHTYELLOW_EX,
        "lightblue": Fore.LIGHTBLUE_EX,
        "lightmagenta": Fore.LIGHTMAGENTA_EX,
        "lightcyan": Fore.LIGHTCYAN_EX,
        "lightwhite": Fore.LIGHTWHITE_EX,
        # Add aliases for flexibility
        "purple": Fore.MAGENTA,
        "pink": Fore.LIGHTMAGENTA_EX,
        "orange": Fore.LIGHTYELLOW_EX,
        "grey": Fore.LIGHTBLACK_EX,
        "gray": Fore.LIGHTBLACK_EX,
    }

    reset = Style.RESET_ALL
    bold_code = Style.BRIGHT if bold else ""
    color_code = color_map.get(color.lower() if color else "", "")

    return f"{color_code}{bold_code}{text}{reset}"
