import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/money.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/widgets/demo_label.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../checkout/data/checkout_models.dart';
import '../../checkout/data/checkout_repository.dart';
import '../../checkout/state/checkout_flow.dart' show couldNotProcessMessage;
import 'payment_chooser.dart';

/// Retry payment for an order in `payment_failed` (Req 13.11, 13.12, 13.13).
class PaymentScreen extends ConsumerStatefulWidget {
  const PaymentScreen({super.key, required this.orderId});
  final String orderId;

  @override
  ConsumerState<PaymentScreen> createState() => _PaymentScreenState();
}

class _PaymentScreenState extends ConsumerState<PaymentScreen> {
  String? _method;
  String? _outcome;
  bool _busy = false;
  String? _error;
  List<StockShortage> _shortages = const [];

  bool get _ready =>
      _method != null && (!methodNeedsOutcome(_method!) || _outcome != null);

  Future<void> _submit() async {
    if (_busy || !_ready) return;
    setState(() {
      _busy = true;
      _error = null;
      _shortages = const [];
    });
    try {
      await ref
          .read(checkoutRepositoryProvider)
          .retryPayment(widget.orderId, _method!, _outcome);
      ref.invalidate(placedOrderProvider(widget.orderId));
      if (mounted) context.go('/confirmation/${widget.orderId}');
    } on ConflictFailure catch (e) {
      final shortages = [
        for (final d in e.details)
          if (d is Map) StockShortage.fromJson(Map<String, dynamic>.from(d)),
      ];
      if (!mounted) return;
      setState(() {
        _busy = false;
        _shortages = shortages;
        _error = shortages.isEmpty
            ? e.message
            : 'Some items are out of stock. The order stays unpaid.';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _busy = false;
        _error = couldNotProcessMessage;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final order = ref.watch(placedOrderProvider(widget.orderId));
    return Scaffold(
      appBar: AppBar(title: const Text('Payment')),
      body: order.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
            message: 'Could not load this order',
            onRetry: () => ref.invalidate(placedOrderProvider(widget.orderId))),
        data: (o) {
          if (!o.canRetryPayment) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  const Text('This order does not need a new payment.'),
                  const SizedBox(height: 12),
                  FilledButton(
                      onPressed: () =>
                          context.go('/confirmation/${widget.orderId}'),
                      child: const Text('View result')),
                ]),
              ),
            );
          }
          return ListView(padding: const EdgeInsets.all(16), children: [
            const Align(
                alignment: Alignment.centerLeft, child: DemoLabel.payment()),
            const SizedBox(height: 12),
            Text('Order ${o.id}',
                style: Theme.of(context).textTheme.titleMedium),
            Text('Amount: ${formatRm(o.totalSen)}'),
            const SizedBox(height: 16),
            PaymentChooser(
              method: _method,
              outcome: _outcome,
              onMethod: (m) => setState(() {
                _method = m;
                if (!methodNeedsOutcome(m)) _outcome = null;
              }),
              onOutcome: (v) => setState(() => _outcome = v),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!,
                  key: const Key('paymentError'),
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
              for (final s in _shortages) Text(s.text),
            ],
            const SizedBox(height: 16),
            FilledButton(
              onPressed: _ready && !_busy ? _submit : null,
              child: Text(_busy ? 'Processing...' : 'Pay (demo)'),
            ),
          ]);
        },
      ),
    );
  }
}
