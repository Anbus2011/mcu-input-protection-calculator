#!/usr/bin/env python3
"""
Resistor Divider Calculator with Zener Clamp Protection Analysis
For STM32 GPIO/ADC input protection circuit design

Entry point for the modular application.
File extension: .div
"""

from src.ui.main_window import MainWindow


def main():
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
