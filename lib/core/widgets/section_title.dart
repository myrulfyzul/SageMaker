import 'package:flutter/material.dart';

import '../legacy_palette.dart';

class SectionTitle extends StatelessWidget {
  const SectionTitle(this.text, {super.key});
  final String text;

  @override
  Widget build(BuildContext context) => Text(
        text,
        style: const TextStyle(
            fontSize: 22, color: deep, fontWeight: FontWeight.w800),
      );
}

/// Centres [child] and limits it to a readable width on wide screens.
Widget bounded(Widget child) => Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 980),
        child: child,
      ),
    );
