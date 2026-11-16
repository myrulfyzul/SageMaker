import 'package:flutter/cupertino.dart' show CupertinoPageTransitionsBuilder;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Brand palette: deep emerald and songket gold on a warm cream base.
const Color kPrimary = Color(0xFF0E3B2E);
const Color kPrimaryLight = Color(0xFF1F6B52);
const Color kSecondary = Color(0xFF87A999);
const Color kBackground = Color(0xFFFAF6EF);
const Color kAccent = Color(0xFFE3B65C);
const Color kCoral = Color(0xFFE07A5F);
const Color kText = Color(0xFF1D2A25);
const Color kMuted = Color(0xFF5E6B66);
const Color kCard = Color(0xFFFFFFFF);
const Color kError = Color(0xFFB3261E);
const Color kSuccess = Color(0xFF2E7D5B);

/// Corner radius for buttons and inputs; cards use [kRadiusLarge]. Both stay
/// within 12 to 16 px (Req 3.2).
const double kRadius = 14;
const double kRadiusLarge = 16;

const String kBodyFont = 'PlusJakartaSans';
const String kDisplayFont = 'PlayfairDisplay';

/// Emerald hero gradient used on banners, headers and KPI cards.
const LinearGradient kHeroGradient = LinearGradient(
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
  colors: [Color(0xFF0B2F25), kPrimary, kPrimaryLight],
  stops: [0, 0.55, 1],
);

/// Gold gradient for highlights and the primary call to action.
const LinearGradient kGoldGradient = LinearGradient(
  begin: Alignment.topLeft,
  end: Alignment.bottomRight,
  colors: [Color(0xFFF2D28B), kAccent, Color(0xFFC9963A)],
);

/// Soft shadow shared by cards and floating surfaces.
List<BoxShadow> softShadow([double opacity = 0.08]) => [
      BoxShadow(
        color: kPrimary.withValues(alpha: opacity),
        blurRadius: 24,
        offset: const Offset(0, 10),
      ),
    ];

/// WCAG contrast ratio between two colours (1 to 21).
double contrastRatio(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  final hi = la > lb ? la : lb;
  final lo = la > lb ? lb : la;
  return (hi + 0.05) / (lo + 0.05);
}

TextTheme _textTheme() {
  const display = TextStyle(fontFamily: kDisplayFont, color: kText);
  const body = TextStyle(fontFamily: kBodyFont, color: kText);
  return TextTheme(
    displayLarge: display.copyWith(fontSize: 52, fontWeight: FontWeight.w700),
    displayMedium: display.copyWith(fontSize: 42, fontWeight: FontWeight.w700),
    displaySmall: display.copyWith(fontSize: 34, fontWeight: FontWeight.w700),
    headlineLarge: display.copyWith(fontSize: 30, fontWeight: FontWeight.w700),
    headlineMedium: display.copyWith(fontSize: 26, fontWeight: FontWeight.w700),
    headlineSmall: display.copyWith(fontSize: 22, fontWeight: FontWeight.w700),
    titleLarge: body.copyWith(fontSize: 20, fontWeight: FontWeight.w700),
    titleMedium: body.copyWith(fontSize: 16, fontWeight: FontWeight.w700),
    titleSmall: body.copyWith(fontSize: 14, fontWeight: FontWeight.w700),
    bodyLarge: body.copyWith(fontSize: 16, height: 1.45),
    bodyMedium: body.copyWith(fontSize: 14, height: 1.45),
    bodySmall: body.copyWith(fontSize: 12, color: kMuted, height: 1.4),
    labelLarge: body.copyWith(fontSize: 14, fontWeight: FontWeight.w700),
    labelMedium: body.copyWith(fontSize: 12, fontWeight: FontWeight.w600),
    labelSmall: body.copyWith(
        fontSize: 11,
        fontWeight: FontWeight.w700,
        letterSpacing: 1.1,
        color: kMuted),
  );
}

ThemeData buildAppTheme() {
  final shape = RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(kRadius),
  );
  final scheme = ColorScheme.fromSeed(seedColor: kPrimary).copyWith(
    primary: kPrimary,
    onPrimary: Colors.white,
    primaryContainer: const Color(0xFFD6EADF),
    onPrimaryContainer: kPrimary,
    secondary: kSecondary,
    onSecondary: kText,
    secondaryContainer: const Color(0xFFE8F0EB),
    onSecondaryContainer: kText,
    tertiary: kAccent,
    onTertiary: kText,
    error: kError,
    surface: kBackground,
    onSurface: kText,
    onSurfaceVariant: kMuted,
    surfaceContainerLowest: kCard,
    surfaceContainerLow: kCard,
    surfaceContainer: kCard,
    surfaceContainerHigh: const Color(0xFFF3EEE4),
    surfaceContainerHighest: const Color(0xFFEDE6D9),
    outline: const Color(0xFFD9D1C3),
    outlineVariant: const Color(0xFFE9E2D5),
    surfaceTint: Colors.transparent,
  );
  OutlineInputBorder border(Color c, [double w = 1]) => OutlineInputBorder(
        borderRadius: BorderRadius.circular(kRadius),
        borderSide: BorderSide(color: c, width: w),
      );
  const buttonPadding = EdgeInsets.symmetric(horizontal: 22, vertical: 16);
  const buttonText = TextStyle(
      fontFamily: kBodyFont, fontWeight: FontWeight.w700, fontSize: 15);
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    fontFamily: kBodyFont,
    scaffoldBackgroundColor: kBackground,
    canvasColor: kBackground,
    textTheme: _textTheme(),
    splashFactory: InkSparkle.splashFactory,
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: FadeForwardsPageTransitionsBuilder(),
      TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
    }),
    appBarTheme: const AppBarTheme(
      backgroundColor: kBackground,
      foregroundColor: kText,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      systemOverlayStyle: SystemUiOverlayStyle.dark,
      titleTextStyle: TextStyle(
          fontFamily: kDisplayFont,
          fontSize: 22,
          fontWeight: FontWeight.w700,
          color: kText),
    ),
    cardTheme: CardThemeData(
      color: kCard,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      shadowColor: kPrimary.withValues(alpha: 0.08),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(kRadiusLarge),
        side: const BorderSide(color: Color(0xFFEFE8DC)),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: kPrimary,
        foregroundColor: Colors.white,
        disabledBackgroundColor: const Color(0xFFD9D1C3),
        padding: buttonPadding,
        textStyle: buttonText,
        shape: shape,
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: kPrimary,
        foregroundColor: Colors.white,
        padding: buttonPadding,
        textStyle: buttonText,
        shape: shape,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: kPrimary,
        side: const BorderSide(color: kPrimary, width: 1.4),
        padding: buttonPadding,
        textStyle: buttonText,
        shape: shape,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
          foregroundColor: kPrimary, textStyle: buttonText, shape: shape),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: kCard,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: border(const Color(0xFFE2DACB)),
      enabledBorder: border(const Color(0xFFE2DACB)),
      focusedBorder: border(kPrimary, 2),
      errorBorder: border(kError),
      focusedErrorBorder: border(kError, 2),
      labelStyle: const TextStyle(color: kMuted),
      floatingLabelStyle: const TextStyle(color: kPrimary),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: kCard,
      selectedColor: kAccent,
      side: const BorderSide(color: Color(0xFFE2DACB)),
      labelStyle: const TextStyle(
          fontFamily: kBodyFont, fontWeight: FontWeight.w600, color: kText),
      shape: StadiumBorder(side: BorderSide.none),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: kCard,
      surfaceTintColor: Colors.transparent,
      indicatorColor: const Color(0xFFD6EADF),
      height: 70,
      elevation: 0,
      labelTextStyle: WidgetStateProperty.resolveWith((s) => TextStyle(
            fontFamily: kBodyFont,
            fontSize: 12,
            fontWeight: s.contains(WidgetState.selected)
                ? FontWeight.w700
                : FontWeight.w500,
            color: s.contains(WidgetState.selected) ? kPrimary : kMuted,
          )),
      iconTheme: WidgetStateProperty.resolveWith((s) => IconThemeData(
            color: s.contains(WidgetState.selected) ? kPrimary : kMuted,
          )),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: kPrimary,
      contentTextStyle:
          const TextStyle(fontFamily: kBodyFont, color: Colors.white),
      shape: shape,
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: kBackground,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
      shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(28))),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: kBackground,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
    ),
    listTileTheme: const ListTileThemeData(
      iconColor: kPrimary,
      contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 2),
    ),
    dividerTheme: const DividerThemeData(color: Color(0xFFEDE6D9), space: 24),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: kPrimary,
      linearTrackColor: Color(0xFFE9E2D5),
    ),
  );
}
