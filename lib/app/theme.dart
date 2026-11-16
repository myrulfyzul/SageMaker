import 'package:flutter/material.dart';

/// Brand colours (Req 3.1).
const Color kPrimary = Color(0xFF123D32);
const Color kSecondary = Color(0xFF87A999);
const Color kBackground = Color(0xFFF8F5EE);
const Color kAccent = Color(0xFFE9C879);
const Color kText = Color(0xFF26332E);
const Color kCard = Color(0xFFFFFFFF);

/// Corner radius for cards, buttons and inputs, within 12 to 16 px (Req 3.2).
const double kRadius = 14;

/// WCAG contrast ratio between two colours (1 to 21).
double contrastRatio(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  final hi = la > lb ? la : lb;
  final lo = la > lb ? lb : la;
  return (hi + 0.05) / (lo + 0.05);
}

ThemeData buildAppTheme() {
  final shape = RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(kRadius),
  );
  final scheme = ColorScheme.fromSeed(seedColor: kPrimary).copyWith(
    primary: kPrimary,
    onPrimary: Colors.white,
    secondary: kSecondary,
    onSecondary: kText,
    tertiary: kAccent,
    onTertiary: kText,
    surface: kBackground,
    onSurface: kText,
    surfaceContainerLowest: kCard,
    surfaceContainerLow: kCard,
    surfaceContainer: kCard,
    surfaceContainerHigh: kCard,
    surfaceContainerHighest: kCard,
    surfaceTint: Colors.transparent,
  );
  OutlineInputBorder border(Color c, [double w = 1]) => OutlineInputBorder(
        borderRadius: BorderRadius.circular(kRadius),
        borderSide: BorderSide(color: c, width: w),
      );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: kBackground,
    canvasColor: kBackground,
    textTheme: Typography.material2021().black.apply(
          bodyColor: kText,
          displayColor: kText,
        ),
    appBarTheme: const AppBarTheme(
      backgroundColor: kPrimary,
      foregroundColor: Colors.white,
      surfaceTintColor: Colors.transparent,
    ),
    cardTheme: CardThemeData(
      color: kCard,
      surfaceTintColor: Colors.transparent,
      elevation: 1,
      shape: shape,
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: kPrimary,
        foregroundColor: Colors.white,
        shape: shape,
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: kPrimary,
        foregroundColor: Colors.white,
        shape: shape,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: kPrimary,
        side: const BorderSide(color: kPrimary),
        shape: shape,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(foregroundColor: kPrimary, shape: shape),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: kCard,
      border: border(kSecondary),
      enabledBorder: border(kSecondary),
      focusedBorder: border(kPrimary, 2),
      errorBorder: border(const Color(0xFF9C2B2B)),
      focusedErrorBorder: border(const Color(0xFF9C2B2B), 2),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: kCard,
      selectedColor: kAccent,
      shape: shape,
    ),
  );
}
