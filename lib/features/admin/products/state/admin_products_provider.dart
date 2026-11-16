import 'dart:typed_data';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../../../core/network/api_client.dart';
import '../data/admin_product_models.dart';
import '../data/admin_products_repository.dart';

final adminProductsRepositoryProvider = Provider<AdminProductsRepository>(
    (ref) => AdminProductsRepository(ref.watch(apiClientProvider)));

/// Staff product list for a name search (Req 20.11). Empty query lists all.
final adminProductsProvider = FutureProvider.autoDispose
    .family<AdminProductPage, String>((ref, q) =>
        ref.watch(adminProductsRepositoryProvider).list(q: q));

/// An image chosen for upload.
class PickedProductImage {
  const PickedProductImage(this.name, this.bytes);
  final String name;
  final Uint8List bytes;
}

/// Opens the gallery for one image; null when cancelled. Overridable in tests.
typedef ProductImagePicker = Future<PickedProductImage?> Function();

final productImagePickerProvider =
    Provider<ProductImagePicker>((ref) => () async {
          final f = await ImagePicker().pickImage(source: ImageSource.gallery);
          if (f == null) return null;
          return PickedProductImage(f.name, await f.readAsBytes());
        });
