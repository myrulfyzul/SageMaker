import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/app_failure.dart';
import '../data/inventory_models.dart';
import '../data/inventory_validation.dart';
import '../state/inventory_provider.dart';

Future<void> showStockItemSheet(BuildContext context, StockItem item) =>
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => StockItemSheet(item: item),
    );

/// Adjust stock with a reason, edit the threshold and read the adjustment
/// history, newest first.
class StockItemSheet extends ConsumerStatefulWidget {
  const StockItemSheet({super.key, required this.item});
  final StockItem item;

  @override
  ConsumerState<StockItemSheet> createState() => _StockItemSheetState();
}

class _StockItemSheetState extends ConsumerState<StockItemSheet> {
  final _adjustKey = GlobalKey<FormState>();
  final _thresholdKey = GlobalKey<FormState>();
  final _delta = TextEditingController();
  final _reason = TextEditingController();
  late final TextEditingController _threshold =
      TextEditingController(text: '${widget.item.threshold}');
  String? _adjustError;
  String? _thresholdError;
  bool _busy = false;

  @override
  void dispose() {
    _delta.dispose();
    _reason.dispose();
    _threshold.dispose();
    super.dispose();
  }

  String _message(AppFailure e) => e is ConflictFailure
      ? (e.code == 'insufficient_stock'
          ? 'Insufficient stock: this change would make stock negative.'
          : e.message)
      : e is ValidationFailure && e.fields.isNotEmpty
          ? e.fields.entries.map((f) => '${f.key}: ${f.value}').join(', ')
          : e.message;

  Future<void> _adjust() async {
    setState(() => _adjustError = null);
    if (!_adjustKey.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      await ref.read(inventoryRepositoryProvider).adjust(
          widget.item.productId, parseDelta(_delta.text), _reason.text);
      ref.invalidate(inventoryProvider);
      ref.invalidate(stockHistoryProvider(widget.item.productId));
      if (mounted) Navigator.of(context).pop();
    } on AppFailure catch (e) {
      if (mounted) setState(() => _adjustError = _message(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _saveThreshold() async {
    setState(() => _thresholdError = null);
    if (!_thresholdKey.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      await ref.read(inventoryRepositoryProvider).setThreshold(
          widget.item.productId, int.parse(_threshold.text.trim()));
      ref.invalidate(inventoryProvider);
      if (mounted) Navigator.of(context).pop();
    } on AppFailure catch (e) {
      if (mounted) setState(() => _thresholdError = _message(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final history = ref.watch(stockHistoryProvider(widget.item.productId));
    final error = TextStyle(color: Theme.of(context).colorScheme.error);
    return Padding(
      padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom,
          left: 16,
          right: 16),
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.item.name,
                style: Theme.of(context).textTheme.titleLarge),
            Text('Stock ${widget.item.quantity}'),
            const SizedBox(height: 16),
            Form(
              key: _adjustKey,
              child: Column(children: [
                TextFormField(
                  controller: _delta,
                  keyboardType: const TextInputType.numberWithOptions(
                      signed: true),
                  decoration: const InputDecoration(
                      labelText: 'Change (for example 5 or -3)'),
                  validator: validateDelta,
                ),
                TextFormField(
                  controller: _reason,
                  decoration: const InputDecoration(labelText: 'Reason'),
                  validator: validateReason,
                ),
              ]),
            ),
            if (_adjustError != null) Text(_adjustError!, style: error),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton(
                  onPressed: _busy ? null : _adjust,
                  child: const Text('Adjust stock')),
            ),
            const Divider(),
            Form(
              key: _thresholdKey,
              child: TextFormField(
                controller: _threshold,
                keyboardType: TextInputType.number,
                decoration:
                    const InputDecoration(labelText: 'Low stock threshold'),
                validator: validateInventoryThreshold,
              ),
            ),
            if (_thresholdError != null) Text(_thresholdError!, style: error),
            Align(
              alignment: Alignment.centerRight,
              child: OutlinedButton(
                  onPressed: _busy ? null : _saveThreshold,
                  child: const Text('Save threshold')),
            ),
            const Divider(),
            Text('Adjustment history',
                style: Theme.of(context).textTheme.titleMedium),
            history.when(
              loading: () => const Padding(
                  padding: EdgeInsets.all(12),
                  child: Center(child: CircularProgressIndicator())),
              error: (e, _) => Row(children: [
                Expanded(
                    child: Text(e is AppFailure ? e.message : 'Server error')),
                TextButton(
                    onPressed: () => ref.invalidate(
                        stockHistoryProvider(widget.item.productId)),
                    child: const Text('Retry')),
              ]),
              data: (rows) => rows.isEmpty
                  ? const Padding(
                      padding: EdgeInsets.symmetric(vertical: 12),
                      child: Text('No adjustments yet.'))
                  : Column(children: [
                      for (final r in rows)
                        ListTile(
                          dense: true,
                          contentPadding: EdgeInsets.zero,
                          title: Text(
                              '${r.delta > 0 ? '+' : ''}${r.delta} · ${r.reason}'),
                          subtitle: Text(
                              [r.actor, r.createdAt]
                                  .where((s) => s.isNotEmpty)
                                  .join(' · ')),
                        ),
                    ]),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    );
  }
}
