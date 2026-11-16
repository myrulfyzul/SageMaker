import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/money.dart';
import '../../../../core/network/app_failure.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../../../../core/widgets/error_view.dart';
import '../../../../core/widgets/loading_view.dart';
import '../../../orders/data/order_models.dart';
import '../data/staff_orders_repository.dart';
import '../state/staff_orders_provider.dart';

/// Message for a rejected status change. A 409 names the current and the
/// requested status (Req 22.7); a 422 shows the length requirement
/// (Req 22.9).
String staffStatusErrorMessage(Object error) {
  if (error is ConflictFailure) {
    for (final d in error.details) {
      if (d is Map && d['current'] != null && d['requested'] != null) {
        return 'Cannot change order status from '
            '${orderStatusLabel(d['current'].toString())} to '
            '${orderStatusLabel(d['requested'].toString())}.';
      }
    }
    return error.message;
  }
  if (error is ValidationFailure) {
    if (error.fields.isNotEmpty) return error.fields.values.join('. ');
    return error.message;
  }
  if (error is NotFoundFailure) return 'Order not found.';
  if (error is AppFailure) return AsyncValueView.defaultErrorMessage(error);
  return 'Something went wrong.';
}

/// Staff order detail with the status actions (Req 22.5 to 22.8).
class StaffOrderDetailScreen extends ConsumerWidget {
  const StaffOrderDetailScreen({super.key, required this.orderId});

  final String orderId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(staffOrderDetailProvider(orderId));
    final notifier = ref.read(staffOrderDetailProvider(orderId).notifier);
    return Scaffold(
      appBar: AppBar(title: Text('Order $orderId')),
      body: !value.hasValue
          ? (value.hasError
              ? ErrorView(
                  message: value.error is NotFoundFailure
                      ? 'Order not found.'
                      : AsyncValueView.defaultErrorMessage(value.error!),
                  onRetry: notifier.retry)
              : const LoadingView())
          : _Detail(
              orderId: orderId,
              state: value.requireValue,
              onRefresh: notifier.refresh),
    );
  }
}

class _Detail extends ConsumerStatefulWidget {
  const _Detail(
      {required this.orderId, required this.state, required this.onRefresh});
  final String orderId;
  final StaffOrderDetailState state;
  final Future<void> Function() onRefresh;

  @override
  ConsumerState<_Detail> createState() => _DetailState();
}

class _DetailState extends ConsumerState<_Detail> {
  bool _busy = false;
  String? _error;

  Future<void> _change(String target) async {
    String? shippingRef;
    String? reason;
    if (target == 'shipped') {
      shippingRef = await _prompt(
        title: 'Shipping reference',
        label: 'Shipping reference (3 to 80 characters)',
        maxLength: 80,
        validator: validateShippingReference,
        confirm: 'Mark as shipped',
        fieldKey: const ValueKey('shipping-reference-field'),
      );
      if (shippingRef == null) return;
    } else if (target == 'cancelled') {
      reason = await _prompt(
        title: 'Cancel order',
        label: 'Reason (3 to 500 characters)',
        maxLength: 500,
        validator: validateCancelReason,
        confirm: 'Cancel order',
        fieldKey: const ValueKey('cancel-reason-field'),
      );
      if (reason == null) return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(staffOrderDetailProvider(widget.orderId).notifier)
          .changeStatus(target,
          shippingReference: shippingRef, reason: reason);
    } on AppFailure catch (e) {
      if (mounted) setState(() => _error = staffStatusErrorMessage(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<String?> _prompt({
    required String title,
    required String label,
    required int maxLength,
    required String? Function(String?) validator,
    required String confirm,
    required Key fieldKey,
  }) =>
      showDialog<String>(
        context: context,
        builder: (_) => _PromptDialog(
            title: title,
            label: label,
            maxLength: maxLength,
            validator: validator,
            confirm: confirm,
            fieldKey: fieldKey),
      );

  @override
  Widget build(BuildContext context) {
    final o = widget.state.order;
    final next = nextStaffStatus(o.status);
    final theme = Theme.of(context);
    return RefreshIndicator(
      onRefresh: widget.onRefresh,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (widget.state.refreshFailed)
            MaterialBanner(
              content: const Text('Refresh failed. Showing the last loaded order.'),
              actions: [
                TextButton(
                    onPressed: widget.onRefresh, child: const Text('Retry')),
              ],
            ),
          Text(orderStatusLabel(o.status),
              key: const ValueKey('detail-status'),
              style: theme.textTheme.headlineSmall),
          const SizedBox(height: 4),
          Text(o.createdAt == null ? '' : formatLocalDateTime(o.createdAt!)),
          const SizedBox(height: 12),
          Text('Customer', style: theme.textTheme.titleMedium),
          Text(o.delivery.name),
          Text(o.delivery.phone),
          Text(o.delivery.email),
          Text([o.delivery.address, o.delivery.postcode, o.delivery.state]
              .whereType<String>()
              .where((e) => e.isNotEmpty)
              .join(', ')),
          if (o.delivery.notes != null) Text('Notes: ${o.delivery.notes}'),
          const SizedBox(height: 12),
          Text('Items', style: theme.textTheme.titleMedium),
          for (final l in o.lines)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text(
                  '${l.name}${l.variationLabel == null ? '' : ' (${l.variationLabel})'}'),
              subtitle: Text('${l.quantity} × ${formatRm(l.unitPriceSen)}'),
              trailing: Text(formatRm(l.lineTotalSen)),
            ),
          Text('Shipping: ${formatRm(o.shippingFeeSen)}'),
          Text('Total: ${formatRm(o.totalSen)}',
              style: theme.textTheme.titleMedium),
          Text('Payment: ${paymentMethodLabel(o.paymentMethod)}, '
              '${paymentStatusLabel(o.paymentStatus)}'),
          if (o.shippingReference != null)
            Text('Shipping reference: ${o.shippingReference}'),
          if (o.productionLabel != null)
            Text('Production: ${o.productionLabel}'),
          const SizedBox(height: 12),
          Text('History', style: theme.textTheme.titleMedium),
          for (final h in o.history)
            Text('${orderStatusLabel(h.status)}'
                '${h.at == null ? '' : ' · ${formatLocalDateTime(h.at!)}'}'),
          const SizedBox(height: 16),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(_error!,
                  key: const ValueKey('status-error'),
                  style: TextStyle(color: theme.colorScheme.error)),
            ),
          if (next != null)
            FilledButton(
              key: const ValueKey('advance-button'),
              onPressed: _busy ? null : () => _change(next),
              child: Text(_busy
                  ? 'Updating…'
                  : next == 'shipped'
                      ? 'Mark as shipped'
                      : 'Mark as ${orderStatusLabel(next).toLowerCase()}'),
            ),
          if (canCancelStaffOrder(o.status))
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: OutlinedButton(
                key: const ValueKey('cancel-button'),
                onPressed: _busy ? null : () => _change('cancelled'),
                child: const Text('Cancel order'),
              ),
            ),
        ],
      ),
    );
  }
}

class _PromptDialog extends StatefulWidget {
  const _PromptDialog({
    required this.title,
    required this.label,
    required this.maxLength,
    required this.validator,
    required this.confirm,
    required this.fieldKey,
  });

  final String title;
  final String label;
  final int maxLength;
  final String? Function(String?) validator;
  final String confirm;
  final Key fieldKey;

  @override
  State<_PromptDialog> createState() => _PromptDialogState();
}

class _PromptDialogState extends State<_PromptDialog> {
  final _controller = TextEditingController();
  final _form = GlobalKey<FormState>();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.title),
        content: Form(
          key: _form,
          child: TextFormField(
            key: widget.fieldKey,
            controller: _controller,
            autofocus: true,
            maxLines: null,
            decoration: InputDecoration(labelText: widget.label),
            validator: widget.validator,
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Back')),
          FilledButton(
            key: const ValueKey('prompt-confirm'),
            onPressed: () {
              if (_form.currentState!.validate()) {
                Navigator.of(context).pop(_controller.text.trim());
              }
            },
            child: Text(widget.confirm),
          ),
        ],
      );
}
