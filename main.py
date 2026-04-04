#!/usr/bin/env python3
"""
MCU Input Protection Calculator
Voltage divider with Zener clamp protection analysis for any MCU GPIO/ADC input.

Entry point for the modular application.
File extension: .div
"""

from src.ui.main_window import MainWindow


def main():
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
