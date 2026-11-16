import 'package:flutter/material.dart';

import '../legacy_palette.dart';

class TotalRow extends StatelessWidget {
  const TotalRow(this.title, this.value, {super.key, this.strong = false});
  final String title;
  final String value;
  final bool strong;
  @override
  Widget build(BuildContext context) => Row(children: [
        Expanded(
            child: Text(title,
                style: TextStyle(
                    fontWeight: strong ? FontWeight.w800 : FontWeight.normal))),
        Text(value,
            style: TextStyle(
                fontWeight: FontWeight.w800,
                fontSize: strong ? 18 : 14,
                color: deep)),
      ]);
}
