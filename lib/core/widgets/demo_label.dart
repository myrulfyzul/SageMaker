import 'package:flutter/material.dart';

/// Demo disclosure label (Req 3.7 to 3.9).
class DemoLabel extends StatelessWidget {
  const DemoLabel(this.text, {super.key});

  /// "Demo" tag shown next to demo products, prices and orders.
  const DemoLabel.item({super.key}) : text = 'Demo';

  /// Prototype disclaimer for the About and login screens.
  const DemoLabel.prototype({super.key})
      : text =
            'Independent university prototype. Not officially Sagemaker.';

  /// Payment simulation notice for payment and confirmation screens.
  const DemoLabel.payment({super.key})
      : text = 'Demo only: payments are simulated.';

  final String text;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: scheme.tertiary,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: scheme.onTertiary,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
