import 'package:flutter/material.dart';

import '../badge.dart';

/// Wraps [child] with a count badge: hidden for 0, `1`-`99`, then `99+`.
class BadgeCount extends StatelessWidget {
  const BadgeCount({super.key, required this.count, required this.child});

  final int count;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final label = badgeLabel(count);
    if (label == null) return child;
    return Badge(label: Text(label), child: child);
  }
}
