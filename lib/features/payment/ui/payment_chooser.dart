import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../checkout/data/checkout_models.dart';

/// Payment method and simulated outcome choice (Req 13.1, 13.2). No real
/// credential input exists here (Req 13.8).
class PaymentChooser extends StatelessWidget {
  const PaymentChooser({
    super.key,
    required this.method,
    required this.outcome,
    required this.onMethod,
    required this.onOutcome,
  });

  final String? method;
  final String? outcome;
  final ValueChanged<String> onMethod;
  final ValueChanged<String> onOutcome;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Payment method', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final m in paymentMethods)
            ChoiceChip(
              label: Text(paymentMethodLabel(m)),
              selected: method == m,
              onSelected: (_) => onMethod(m),
            ),
        ]),
        if (method != null && methodNeedsOutcome(method!)) ...[
          const SizedBox(height: 16),
          Text('Simulated outcome (demo)',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: [
            for (final o in simulatedOutcomes)
              ChoiceChip(
                label: Text(outcomeLabel(o)),
                selected: outcome == o,
                onSelected: (_) => onOutcome(o),
              ),
          ]),
        ],
        if (method == 'cod')
          const Padding(
            padding: EdgeInsets.only(top: 12),
            child: Text(
                'Pay on delivery. The order is placed and recorded as pending cash on delivery.'),
          ),
        if (method == 'card') const DemoCardField(),
      ],
    );
  }
}

/// Non-functional demo card field. Its value is never transmitted and is
/// cleared when the screen closes (Req 13.9).
class DemoCardField extends StatefulWidget {
  const DemoCardField({super.key});

  @override
  State<DemoCardField> createState() => _DemoCardFieldState();
}

class _DemoCardFieldState extends State<DemoCardField> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.clear();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: TextField(
        key: const Key('demoCardField'),
        controller: _controller,
        keyboardType: TextInputType.number,
        autocorrect: false,
        enableSuggestions: false,
        autofillHints: null,
        inputFormatters: [
          FilteringTextInputFormatter.digitsOnly,
          LengthLimitingTextInputFormatter(19),
        ],
        decoration: const InputDecoration(
          labelText: 'Card number (demo field, not functional)',
          helperText: 'Do not enter a real card. This value is never sent or saved.',
          border: OutlineInputBorder(),
        ),
      ),
    );
  }
}
