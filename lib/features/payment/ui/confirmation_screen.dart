import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/money.dart';
import '../../../core/widgets/demo_label.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../checkout/data/checkout_models.dart';
import '../../checkout/data/checkout_repository.dart';

/// Title and message matching the payment outcome (Req 13.10).
({String title, String message, IconData icon}) confirmationCopy(
    PlacedOrder o) {
  switch (o.paymentStatus) {
    case 'paid':
      return (
        title: 'Payment successful',
        message: 'Your demo payment succeeded and the order is placed.',
        icon: Icons.check_circle_outline,
      );
    case 'pending_cod':
      return (
        title: 'Order placed',
        message: 'Pay cash on delivery. The payment is recorded as pending.',
        icon: Icons.local_shipping_outlined,
      );
    case 'cancelled':
      return (
        title: 'Payment cancelled',
        message: 'The payment was cancelled and the order is cancelled.',
        icon: Icons.cancel_outlined,
      );
    default:
      return (
        title: 'Payment failed',
        message: 'The payment failed. You can retry the payment.',
        icon: Icons.error_outline,
      );
  }
}

/// Result screen after checkout or a payment retry (Req 3.8, 13.10).
class ConfirmationScreen extends ConsumerWidget {
  const ConfirmationScreen({super.key, required this.orderId});
  final String orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final order = ref.watch(placedOrderProvider(orderId));
    return Scaffold(
      appBar: AppBar(title: const Text('Order confirmation')),
      body: order.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
            message: 'Could not load this order',
            onRetry: () => ref.invalidate(placedOrderProvider(orderId))),
        data: (o) {
          final copy = confirmationCopy(o);
          return ListView(padding: const EdgeInsets.all(16), children: [
            const Align(
                alignment: Alignment.centerLeft, child: DemoLabel.payment()),
            const SizedBox(height: 16),
            Icon(copy.icon, size: 56, semanticLabel: copy.title),
            const SizedBox(height: 8),
            Text(copy.title,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.headlineSmall),
            const SizedBox(height: 4),
            Text(copy.message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            Text('Order ${o.id}',
                style: Theme.of(context).textTheme.titleMedium),
            for (final l in o.lines)
              Text(
                  '${l.quantity} x ${l.name}${l.variationLabel == null ? '' : ' (${l.variationLabel})'}  ${formatRm(l.lineTotalSen)}'),
            const SizedBox(height: 8),
            Text('Total: ${formatRm(o.totalSen)}',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 24),
            if (o.canRetryPayment)
              FilledButton(
                  onPressed: () => context.go('/payment/${o.id}'),
                  child: const Text('Retry payment')),
            if (o.canRetryPayment) const SizedBox(height: 8),
            OutlinedButton(
                onPressed: () => context.go('/shop'),
                child: const Text('Return to shop')),
          ]);
        },
      ),
    );
  }
}
