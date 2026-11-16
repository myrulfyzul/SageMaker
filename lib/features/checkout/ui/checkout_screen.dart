import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants.dart';
import '../../../core/money.dart';
import '../../../core/widgets/demo_label.dart';
import '../../../core/widgets/empty_view.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../payment/ui/payment_chooser.dart';
import '../data/checkout_models.dart';
import '../data/checkout_repository.dart';
import '../state/checkout_flow.dart';

/// Four-step checkout: cart review, delivery details, payment method,
/// confirmation (Req 12.1).
class CheckoutScreen extends ConsumerWidget {
  const CheckoutScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(checkoutFlowProvider);
    final cart = ref.watch(checkoutCartProvider);
    final address = ref.watch(defaultAddressProvider);

    // Prefill once from the default address (Req 12.5). A failed address
    // lookup just leaves the form blank.
    if (!flow.prefilled && !address.isLoading) {
      final value = address.hasError ? null : address.value;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (context.mounted) {
          ref.read(checkoutFlowProvider.notifier).prefill(value);
        }
      });
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Checkout')),
      body: cart.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
            message: 'Could not load your cart',
            onRetry: () => ref.invalidate(checkoutCartProvider)),
        data: (c) {
          if (c.isEmpty) {
            return EmptyView(
                message: 'Your cart is empty.',
                actionLabel: 'Browse products',
                onAction: () => context.go('/shop'));
          }
          return Column(children: [
            _StepHeader(step: flow.step),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  switch (flow.step) {
                    0 => _CartReview(cart: c),
                    1 => _DeliveryStep(
                        key: ValueKey('delivery-${flow.formVersion}')),
                    2 => const _PaymentStep(),
                    _ => _ConfirmStep(cart: c),
                  },
                ],
              ),
            ),
            _StepButtons(cart: c),
          ]);
        },
      ),
    );
  }
}

class _StepHeader extends StatelessWidget {
  const _StepHeader({required this.step});
  final int step;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Step ${step + 1} of 4: ${checkoutStepTitles[step]}',
            key: const Key('stepTitle'),
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        LinearProgressIndicator(value: (step + 1) / 4),
      ]),
    );
  }
}

class _StepButtons extends ConsumerWidget {
  const _StepButtons({required this.cart});
  final CheckoutCart cart;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(checkoutFlowProvider);
    final notifier = ref.read(checkoutFlowProvider.notifier);
    final blocked = flow.step == 0 && cart.hasUnavailable;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (flow.error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(flow.error!,
                  key: const Key('checkoutError'),
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          for (final s in flow.shortages) Text(s.text),
          Row(children: [
            if (flow.step > 0)
              Padding(
                padding: const EdgeInsets.only(right: 8),
                child: OutlinedButton(
                    onPressed: flow.submitting
                        ? null
                        : () => notifier.goTo(flow.step - 1),
                    child: const Text('Back')),
              ),
            Expanded(
              child: FilledButton(
                key: const Key('stepNext'),
                onPressed: blocked || flow.submitting
                    ? null
                    : () async {
                        switch (flow.step) {
                          case 0:
                            notifier.goTo(1);
                          case 1:
                            notifier.continueFromDelivery();
                          case 2:
                            notifier.continueFromPayment();
                          default:
                            final id = await notifier.submit();
                            if (id != null && context.mounted) {
                              context.go('/confirmation/$id');
                            }
                        }
                      },
                child: Text(switch (flow.step) {
                  0 => 'Continue to delivery',
                  1 => 'Continue to payment',
                  2 => 'Review order',
                  _ => flow.submitting ? 'Placing order...' : 'Place order (demo)',
                }),
              ),
            ),
          ]),
        ]),
      ),
    );
  }
}

class _CartReview extends StatelessWidget {
  const _CartReview({required this.cart});
  final CheckoutCart cart;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final l in cart.lines)
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(l.name),
          subtitle: Text(l.available
              ? '${l.variationLabel ?? ''} Qty ${l.quantity}'.trim()
              : 'No longer available. Remove it from your cart to continue.'),
          trailing: Text(formatRm(l.lineTotalSen)),
        ),
      const Divider(),
      _TotalLines(cart: cart),
      if (cart.hasUnavailable)
        TextButton(
            onPressed: () => context.go('/cart'),
            child: const Text('Back to cart')),
    ]);
  }
}

class _TotalLines extends StatelessWidget {
  const _TotalLines({required this.cart});
  final CheckoutCart cart;

  Widget _row(String a, String b, {bool bold = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 2),
        child: Row(children: [
          Expanded(
              child: Text(a,
                  style: TextStyle(
                      fontWeight: bold ? FontWeight.bold : FontWeight.normal))),
          Text(b,
              style: TextStyle(
                  fontWeight: bold ? FontWeight.bold : FontWeight.normal)),
        ]),
      );

  @override
  Widget build(BuildContext context) => Column(children: [
        _row('Subtotal', formatRm(cart.subtotalSen)),
        _row('Delivery', formatRm(cart.deliveryFeeSen)),
        _row('Total', formatRm(cart.grandTotalSen), bold: true),
      ]);
}

class _DeliveryStep extends ConsumerStatefulWidget {
  const _DeliveryStep({super.key});

  @override
  ConsumerState<_DeliveryStep> createState() => _DeliveryStepState();
}

class _DeliveryStepState extends ConsumerState<_DeliveryStep> {
  late final Map<String, TextEditingController> _c;

  @override
  void initState() {
    super.initState();
    final f = ref.read(checkoutFlowProvider).delivery;
    _c = {
      'name': TextEditingController(text: f.name),
      'phone': TextEditingController(text: f.phone),
      'email': TextEditingController(text: f.email),
      'address': TextEditingController(text: f.address),
      'postcode': TextEditingController(text: f.postcode),
      'notes': TextEditingController(text: f.notes),
    };
  }

  @override
  void dispose() {
    for (final c in _c.values) {
      c.dispose();
    }
    super.dispose();
  }

  void _push({String? state}) {
    ref.read(checkoutFlowProvider.notifier).updateDelivery(DeliveryForm(
          name: _c['name']!.text,
          phone: _c['phone']!.text,
          email: _c['email']!.text,
          address: _c['address']!.text,
          postcode: _c['postcode']!.text,
          state: state ?? ref.read(checkoutFlowProvider).delivery.state,
          notes: _c['notes']!.text,
        ));
  }

  Widget _field(String key, String label,
      {TextInputType? type, int maxLines = 1, int? maxLength}) {
    final errors = ref.watch(checkoutFlowProvider.select((s) => s.errors));
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextField(
        key: Key('field-$key'),
        controller: _c[key],
        keyboardType: type,
        maxLines: maxLines,
        maxLength: maxLength,
        onChanged: (_) => _push(),
        decoration: InputDecoration(
          labelText: label,
          errorText: errors[key],
          border: const OutlineInputBorder(),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final flow = ref.watch(checkoutFlowProvider);
    final stateValue = malaysianStates.contains(flow.delivery.state)
        ? flow.delivery.state
        : null;
    return Column(children: [
      _field('name', 'Full name'),
      _field('phone', 'Phone', type: TextInputType.phone),
      _field('email', 'Email', type: TextInputType.emailAddress),
      _field('address', 'Address', maxLines: 3),
      _field('postcode', 'Postcode', type: TextInputType.number),
      Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: DropdownButtonFormField<String>(
          key: Key('field-state-${flow.formVersion}'),
          initialValue: stateValue,
          isExpanded: true,
          decoration: InputDecoration(
            labelText: 'State',
            errorText: flow.errors['state'],
            border: const OutlineInputBorder(),
          ),
          items: [
            for (final s in malaysianStates)
              DropdownMenuItem(value: s, child: Text(s)),
          ],
          onChanged: (v) => _push(state: v ?? ''),
        ),
      ),
      _field('notes', 'Delivery notes (optional)', maxLines: 2, maxLength: 500),
    ]);
  }
}

class _PaymentStep extends ConsumerWidget {
  const _PaymentStep();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(checkoutFlowProvider);
    final notifier = ref.read(checkoutFlowProvider.notifier);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const DemoLabel.payment(),
      const SizedBox(height: 12),
      PaymentChooser(
        method: flow.method,
        outcome: flow.outcome,
        onMethod: notifier.chooseMethod,
        onOutcome: notifier.chooseOutcome,
      ),
    ]);
  }
}

class _ConfirmStep extends ConsumerWidget {
  const _ConfirmStep({required this.cart});
  final CheckoutCart cart;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final flow = ref.watch(checkoutFlowProvider);
    final d = flow.delivery;
    final method = flow.method;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const DemoLabel.payment(),
      const SizedBox(height: 12),
      Text('Deliver to', style: Theme.of(context).textTheme.titleMedium),
      Text('${d.name}\n${d.address}\n${d.postcode} ${d.state}\n${d.phone}\n${d.email}'),
      if (d.notes.trim().isNotEmpty) Text('Notes: ${d.notes.trim()}'),
      const SizedBox(height: 12),
      Text('Payment', style: Theme.of(context).textTheme.titleMedium),
      Text(method == null
          ? ''
          : '${paymentMethodLabel(method)}'
              '${flow.outcome == null ? '' : ', simulated outcome: ${outcomeLabel(flow.outcome!)}'}'),
      const SizedBox(height: 12),
      _TotalLines(cart: cart),
    ]);
  }
}
