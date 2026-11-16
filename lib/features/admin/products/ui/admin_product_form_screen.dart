import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/app_failure.dart';
import '../../../catalogue/data/catalogue_models.dart';
import '../../../catalogue/state/shop_provider.dart';
import '../data/admin_product_models.dart';
import '../data/admin_product_validation.dart';
import '../state/admin_products_provider.dart';

/// Create and edit form (Req 20.1, 20.2, 20.5, 20.11, 20.12). On a rejected
/// save the reason is shown, the values stay and the form stays open.
/// Pops with `true` once saved.
class AdminProductFormScreen extends ConsumerStatefulWidget {
  const AdminProductFormScreen({super.key, this.product});

  /// Null to create.
  final AdminProduct? product;

  @override
  ConsumerState<AdminProductFormScreen> createState() => _FormState();
}

class _FormState extends ConsumerState<AdminProductFormScreen> {
  final _key = GlobalKey<FormState>();
  late final TextEditingController _name;
  late final TextEditingController _description;
  late final TextEditingController _price;
  late final TextEditingController _stock;
  late final TextEditingController _threshold;
  int? _categoryId;
  PickedProductImage? _pending;
  String? _imageError;
  String? _formError;
  Map<String, String> _serverErrors = {};
  bool _saving = false;

  /// Set once the product exists on the server, so a retry after a failed
  /// image upload updates instead of creating a duplicate.
  String? _savedId;

  @override
  void initState() {
    super.initState();
    final p = widget.product;
    _savedId = p?.id;
    _name = TextEditingController(text: p?.name ?? '');
    _description = TextEditingController(text: p?.description ?? '');
    _price = TextEditingController(
        text: p == null
            ? ''
            : '${p.priceSen ~/ 100}.${(p.priceSen % 100).toString().padLeft(2, '0')}');
    _stock = TextEditingController(text: p == null ? '' : '${p.stock}');
    _threshold =
        TextEditingController(text: p == null ? '0' : '${p.lowStockThreshold}');
    _categoryId = p?.categoryId;
  }

  @override
  void dispose() {
    _name.dispose();
    _description.dispose();
    _price.dispose();
    _stock.dispose();
    _threshold.dispose();
    super.dispose();
  }

  String? _check(String field, String? local) => local ?? _serverErrors[field];

  Future<void> _pickImage() async {
    final picked = await ref.read(productImagePickerProvider)();
    if (picked == null) return;
    final error = validateImage(picked.name, picked.bytes.length);
    setState(() {
      _imageError = error;
      if (error == null) _pending = picked;
    });
  }

  Future<void> _save() async {
    setState(() {
      _serverErrors = {};
      _formError = null;
    });
    if (!_key.currentState!.validate()) return;
    final categoryId = _categoryId;
    if (categoryId == null) return;
    final input = ProductInput(
      name: _name.text,
      description: _description.text,
      categoryId: categoryId,
      priceSen: parsePriceSen(_price.text)!,
      stock: int.parse(_stock.text.trim()),
      lowStockThreshold: int.parse(_threshold.text.trim()),
    );
    setState(() => _saving = true);
    final repo = ref.read(adminProductsRepositoryProvider);
    try {
      final saved = _savedId == null
          ? await repo.create(input)
          : await repo.update(_savedId!, input);
      _savedId = saved.id;
      if (_pending != null) {
        await repo.uploadImage(saved.id, _pending!.name, _pending!.bytes);
        _pending = null;
      }
      if (mounted) Navigator.of(context).pop(true);
    } on ValidationFailure catch (e) {
      if (!mounted) return;
      setState(() {
        _serverErrors = {
          for (final entry in e.fields.entries)
            _fieldKey(entry.key): entry.value
        };
        _formError = e.message;
      });
      WidgetsBinding.instance
          .addPostFrameCallback((_) => _key.currentState?.validate());
    } on AppFailure catch (e) {
      if (!mounted) return;
      setState(() => _formError = _savedId != null && _pending != null
          ? 'Product saved, but the image was rejected: ${e.message}'
          : e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  static String _fieldKey(String serverField) => switch (serverField) {
        'category_id' || 'categoryId' || 'category' => 'category',
        'price_sen' || 'priceSen' || 'price' => 'price',
        'low_stock_threshold' || 'lowStockThreshold' => 'threshold',
        final other => other,
      };

  @override
  Widget build(BuildContext context) {
    final categories = ref.watch(categoriesProvider);
    final editing = widget.product != null;
    return Scaffold(
      appBar: AppBar(title: Text(editing ? 'Edit product' : 'New product')),
      body: Form(
        key: _key,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_formError != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Text(_formError!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
            TextFormField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Name'),
              validator: (v) => _check('name', validateProductName(v)),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _description,
              maxLines: 4,
              decoration: const InputDecoration(labelText: 'Description'),
              validator: (v) =>
                  _check('description', validateProductDescription(v)),
            ),
            const SizedBox(height: 12),
            categories.when(
              data: (list) => DropdownButtonFormField<int>(
                initialValue:
                    list.any((c) => c.id == _categoryId) ? _categoryId : null,
                decoration: const InputDecoration(labelText: 'Category'),
                items: [
                  for (final CategoryRef c in list)
                    DropdownMenuItem(value: c.id, child: Text(c.name)),
                ],
                onChanged: (v) => setState(() => _categoryId = v),
                validator: (v) =>
                    _check('category', v == null ? 'Choose a category' : null),
              ),
              loading: () => const LinearProgressIndicator(),
              error: (e, _) => Row(children: [
                const Expanded(child: Text('Could not load categories')),
                TextButton(
                    onPressed: () => ref.invalidate(categoriesProvider),
                    child: const Text('Retry')),
              ]),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _price,
              keyboardType:
                  const TextInputType.numberWithOptions(decimal: true),
              decoration: const InputDecoration(
                  labelText: 'Price (RM)', prefixText: 'RM '),
              validator: (v) => _check('price', validatePriceRm(v)),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _stock,
              keyboardType: TextInputType.number,
              decoration: const InputDecoration(labelText: 'Stock'),
              validator: (v) => _check('stock', validateStock(v)),
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _threshold,
              keyboardType: TextInputType.number,
              decoration:
                  const InputDecoration(labelText: 'Low stock threshold'),
              validator: (v) => _check('threshold', validateThreshold(v)),
            ),
            const SizedBox(height: 16),
            Text('Images', style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),
            if (editing && widget.product!.imageUrls.isNotEmpty)
              SizedBox(
                height: 72,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  children: [
                    for (final url in widget.product!.imageUrls)
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: Image.network(url,
                            width: 72,
                            height: 72,
                            fit: BoxFit.cover,
                            webHtmlElementStrategy: WebHtmlElementStrategy.prefer,
                            semanticLabel: 'Product image',
                            errorBuilder: (_, __, ___) =>
                                const Icon(Icons.broken_image)),
                      ),
                  ],
                ),
              ),
            Row(children: [
              OutlinedButton.icon(
                onPressed: _saving ? null : _pickImage,
                icon: const Icon(Icons.add_photo_alternate_outlined),
                label: const Text('Add image'),
              ),
              const SizedBox(width: 12),
              if (_pending != null)
                Expanded(
                    child:
                        Text(_pending!.name, overflow: TextOverflow.ellipsis)),
            ]),
            if (_imageError != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(_imageError!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(editing || _savedId != null
                      ? 'Save changes'
                      : 'Create product'),
            ),
          ],
        ),
      ),
    );
  }
}
