import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/app_failure.dart';
import '../data/custom_order_validation.dart';
import '../data/custom_orders_repository.dart';
import '../state/custom_orders_provider.dart';

/// Request form: product type, description, quantity, preferred date and up
/// to 5 reference images (Req 16.1, 16.2, 16.3, 16.8).
class CustomOrderFormScreen extends ConsumerStatefulWidget {
  const CustomOrderFormScreen({super.key});

  @override
  ConsumerState<CustomOrderFormScreen> createState() => _FormState();
}

class _FormState extends ConsumerState<CustomOrderFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _type = TextEditingController();
  final _description = TextEditingController();
  final _quantity = TextEditingController();
  DateTime? _date;
  bool _dateTouched = false;
  final List<PickedImage> _images = [];
  String? _imageError;
  Map<String, String> _serverErrors = const {};
  String? _submitError;
  bool _submitting = false;

  @override
  void dispose() {
    _type.dispose();
    _description.dispose();
    _quantity.dispose();
    super.dispose();
  }

  Future<void> _pickImages() async {
    final room = maxCustomOrderImages - _images.length;
    if (room <= 0) {
      setState(() => _imageError = 'You can attach at most 5 images');
      return;
    }
    final picked = await ref.read(imagePickerProvider)(room);
    final errors = <String>[];
    for (final p in picked) {
      if (_images.length >= maxCustomOrderImages) {
        errors.add('You can attach at most 5 images');
        break;
      }
      final e = validateImage(p.name, p.bytes.length);
      if (e == null) {
        _images.add(p);
      } else {
        errors.add(e);
      }
    }
    if (!mounted) return;
    setState(() => _imageError = errors.isEmpty ? null : errors.join('\n'));
  }

  Future<void> _pickDate() async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: _date ?? now,
      firstDate: DateTime(now.year, now.month, now.day),
      lastDate: DateTime(now.year + 3),
    );
    if (picked != null) setState(() => _date = picked);
  }

  Future<void> _submit() async {
    setState(() {
      _dateTouched = true;
      _serverErrors = const {};
      _submitError = null;
    });
    final valid = _formKey.currentState!.validate();
    if (!valid || validatePreferredDate(_date) != null) return;
    setState(() => _submitting = true);
    try {
      await ref.read(customOrdersRepositoryProvider).create(
            productType: _type.text,
            description: _description.text,
            quantity: int.parse(_quantity.text.trim()),
            preferredDate: formatApiDate(_date!),
            images: _images,
          );
      ref.invalidate(customOrdersProvider);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Request submitted')));
      context.pop();
    } on ValidationFailure catch (e) {
      if (!mounted) return;
      setState(() {
        _serverErrors = e.fields;
        _submitError = e.fields.isEmpty ? e.message : null;
      });
    } on AppFailure catch (e) {
      if (!mounted) return;
      setState(() => _submitError = switch (e) {
            NetworkFailure() => 'Network unavailable. Please try again.',
            TimeoutFailure() => 'Request timed out. Please try again.',
            _ => e.message,
          });
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String? _imagesServerError() {
    final msgs = [
      for (final e in _serverErrors.entries)
        if (e.key.startsWith('images')) e.value
    ];
    return msgs.isEmpty ? null : msgs.join('\n');
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final dateError =
        _dateTouched ? validatePreferredDate(_date) : _serverErrors['preferredDate'];
    final imagesError = _imageError ?? _imagesServerError();
    return Scaffold(
      appBar: AppBar(title: const Text('New custom order')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextFormField(
              controller: _type,
              decoration: InputDecoration(
                  labelText: 'Product type',
                  errorText: _serverErrors['productType']),
              validator: validateProductType,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _description,
              decoration: InputDecoration(
                  labelText: 'Description',
                  errorText: _serverErrors['description']),
              minLines: 3,
              maxLines: 6,
              validator: validateDescription,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _quantity,
              decoration: InputDecoration(
                  labelText: 'Quantity', errorText: _serverErrors['quantity']),
              keyboardType: TextInputType.number,
              validator: validateQuantity,
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: _pickDate,
              icon: const Icon(Icons.event),
              label: Text(_date == null
                  ? 'Preferred date'
                  : 'Preferred date: ${formatApiDate(_date!)}'),
            ),
            if (dateError != null)
              Padding(
                padding: const EdgeInsets.only(top: 4, left: 12),
                child: Text(dateError,
                    key: const ValueKey('date-error'),
                    style: TextStyle(color: scheme.error, fontSize: 12)),
              ),
            const SizedBox(height: 16),
            Text('Reference images (${_images.length}/$maxCustomOrderImages)',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            const Text('PNG, JPEG or WebP, up to 5 MB each.'),
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              for (var i = 0; i < _images.length; i++)
                InputChip(
                  key: ValueKey('image-$i'),
                  label: Text(_images[i].name),
                  deleteButtonTooltipMessage: 'Remove image',
                  onDeleted: () => setState(() => _images.removeAt(i)),
                ),
            ]),
            OutlinedButton.icon(
              onPressed: _pickImages,
              icon: const Icon(Icons.add_photo_alternate_outlined),
              label: const Text('Add images'),
            ),
            if (imagesError != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(imagesError,
                    key: const ValueKey('image-error'),
                    style: TextStyle(color: scheme.error, fontSize: 12)),
              ),
            if (_submitError != null)
              Padding(
                padding: const EdgeInsets.only(top: 12),
                child: Text(_submitError!,
                    key: const ValueKey('submit-error'),
                    style: TextStyle(color: scheme.error)),
              ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: _submitting ? null : _submit,
              child: _submitting
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Submit request'),
            ),
          ],
        ),
      ),
    );
  }
}
