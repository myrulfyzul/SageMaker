import 'package:flutter/material.dart';

/// Icon-only button that requires a non-empty semantic label (Req 3.11).
class AppIconButton extends StatelessWidget {
  AppIconButton({
    super.key,
    required this.icon,
    required this.semanticLabel,
    required this.onPressed,
  }) : assert(semanticLabel.trim().isNotEmpty, 'semanticLabel must not be empty');

  final IconData icon;
  final String semanticLabel;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return IconButton(
      icon: Icon(icon),
      tooltip: semanticLabel,
      onPressed: onPressed,
    );
  }
}
