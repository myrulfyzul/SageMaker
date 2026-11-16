import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/app_failure.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../state/staff_settings_provider.dart';

/// Staff settings: the default low-stock threshold.
class StaffSettingsScreen extends ConsumerWidget {
  const StaffSettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(defaultThresholdProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: AsyncValueView<int>(
        value: value,
        onRetry: () => ref.invalidate(defaultThresholdProvider),
        onEmptyAction: () {},
        errorMessage: (e) => e is AppFailure ? e.message : 'Server error',
        data: (t) => _Form(initial: t),
      ),
    );
  }
}

class _Form extends ConsumerStatefulWidget {
  const _Form({required this.initial});
  final int initial;

  @override
  ConsumerState<_Form> createState() => _FormState();
}

class _FormState extends ConsumerState<_Form> {
  late final _c = TextEditingController(text: '${widget.initial}');
  final _key = GlobalKey<FormState>();
  String? _serverError;
  bool _saving = false;
  bool _saved = false;

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_key.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _serverError = null;
      _saved = false;
    });
    try {
      final v = await ref
          .read(staffSettingsRepositoryProvider)
          .setThreshold(int.parse(_c.text.trim()));
      _c.text = '$v';
      ref.invalidate(defaultThresholdProvider);
      if (mounted) setState(() => _saved = true);
    } on AppFailure catch (e) {
      if (mounted) {
        setState(() => _serverError =
            e is ValidationFailure && e.fields.isNotEmpty
                ? e.fields.values.first
                : e.message);
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) => Form(
        key: _key,
        child: ListView(padding: const EdgeInsets.all(16), children: [
          TextFormField(
            key: const ValueKey('default-threshold'),
            controller: _c,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(
              labelText: 'Default low-stock threshold',
              helperText: 'Used for products without their own threshold',
            ),
            validator: validateDefaultThreshold,
          ),
          if (_serverError != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_serverError!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          if (_saved)
            const Padding(
                padding: EdgeInsets.only(top: 8), child: Text('Settings saved.')),
          const SizedBox(height: 16),
          FilledButton(
              onPressed: _saving ? null : _save, child: const Text('Save')),
        ]),
      );
}
