import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/constants.dart';
import '../../../core/network/app_failure.dart';
import '../../../core/validators.dart';
import '../state/profile_provider.dart';

/// Add or edit a saved address. Returns true when it was saved.
Future<bool?> showAddressForm(BuildContext context, {SavedAddress? existing}) =>
    showDialog<bool>(
      context: context,
      builder: (_) => AddressFormDialog(existing: existing),
    );

class AddressFormDialog extends ConsumerStatefulWidget {
  const AddressFormDialog({super.key, this.existing});
  final SavedAddress? existing;

  @override
  ConsumerState<AddressFormDialog> createState() => _AddressFormState();
}

class _AddressFormState extends ConsumerState<AddressFormDialog> {
  final _key = GlobalKey<FormState>();
  late final _recipient =
      TextEditingController(text: widget.existing?.recipientName);
  late final _phone = TextEditingController(text: widget.existing?.phone);
  late final _line1 = TextEditingController(text: widget.existing?.line1);
  late final _line2 = TextEditingController(text: widget.existing?.line2);
  late final _postcode = TextEditingController(text: widget.existing?.postcode);
  late final _city = TextEditingController(text: widget.existing?.city);
  late String? _state = malaysianStates.contains(widget.existing?.state)
      ? widget.existing!.state
      : null;
  late bool _default = widget.existing?.isDefault ?? false;
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    for (final c in [_recipient, _phone, _line1, _line2, _postcode, _city]) {
      c.dispose();
    }
    super.dispose();
  }

  String? _required(String? v, int max) {
    final t = v?.trim() ?? '';
    if (t.isEmpty || t.length > max) return 'Required, at most $max characters';
    return null;
  }

  Future<void> _save() async {
    if (!_key.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    final body = addressBody(
      recipientName: _recipient.text,
      phone: _phone.text,
      line1: _line1.text,
      line2: _line2.text,
      postcode: _postcode.text,
      city: _city.text,
      state: _state!,
      isDefault: _default,
    );
    final repo = ref.read(profileRepositoryProvider);
    try {
      if (widget.existing == null) {
        await repo.create(body);
      } else {
        await repo.updateAddress(widget.existing!.id, body);
      }
      if (mounted) Navigator.of(context).pop(true);
    } on ValidationFailure catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = e.fields.isEmpty
            ? e.message
            : e.fields.entries.map((f) => '${f.key}: ${f.value}').join('\n');
      });
    } on AppFailure catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.existing == null ? 'Add address' : 'Edit address'),
      content: SingleChildScrollView(
        child: Form(
          key: _key,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextFormField(
                  key: const ValueKey('addr-recipient'),
                  controller: _recipient,
                  decoration: const InputDecoration(labelText: 'Recipient name'),
                  validator: (v) => _required(v, 100)),
              TextFormField(
                  key: const ValueKey('addr-phone'),
                  controller: _phone,
                  keyboardType: TextInputType.phone,
                  decoration: const InputDecoration(labelText: 'Phone'),
                  validator: validateProfilePhone),
              TextFormField(
                  key: const ValueKey('addr-line1'),
                  controller: _line1,
                  decoration: const InputDecoration(labelText: 'Address line 1'),
                  validator: (v) => _required(v, 200)),
              TextFormField(
                  key: const ValueKey('addr-line2'),
                  controller: _line2,
                  decoration:
                      const InputDecoration(labelText: 'Address line 2 (optional)'),
                  validator: (v) => (v?.trim().length ?? 0) > 200
                      ? 'At most 200 characters'
                      : null),
              TextFormField(
                  key: const ValueKey('addr-postcode'),
                  controller: _postcode,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'Postcode'),
                  validator: validatePostcode),
              TextFormField(
                  key: const ValueKey('addr-city'),
                  controller: _city,
                  decoration: const InputDecoration(labelText: 'City'),
                  validator: (v) => _required(v, 100)),
              DropdownButtonFormField<String>(
                key: const ValueKey('addr-state'),
                initialValue: _state,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'State'),
                items: [
                  for (final s in malaysianStates)
                    DropdownMenuItem(value: s, child: Text(s)),
                ],
                onChanged: (v) => setState(() => _state = v),
                validator: validateState,
              ),
              SwitchListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Default address'),
                value: _default,
                onChanged: (v) => setState(() => _default = v),
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(_error!,
                      style: TextStyle(
                          color: Theme.of(context).colorScheme.error)),
                ),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
            onPressed: _saving ? null : () => Navigator.of(context).pop(false),
            child: const Text('Cancel')),
        FilledButton(
            onPressed: _saving ? null : _save, child: const Text('Save')),
      ],
    );
  }
}
