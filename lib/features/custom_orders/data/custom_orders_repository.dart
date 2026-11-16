import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../../../core/network/api_client.dart';
import 'custom_order_models.dart';

/// An image chosen by the customer, read into memory.
class PickedImage {
  const PickedImage(this.name, this.bytes);
  final String name;
  final Uint8List bytes;
}

/// `/api/custom-orders` for the signed-in customer.
class CustomOrdersRepository {
  CustomOrdersRepository(this._client);

  final ApiClient _client;

  Future<CustomOrderPage> list({int offset = 0, int limit = 20}) async {
    final body = await _client
        .get('/api/custom-orders', query: {'limit': limit, 'offset': offset});
    return CustomOrderPage.fromJson(Map<String, dynamic>.from(body as Map));
  }

  Future<CustomOrder> get(int id) async {
    final body = await _client.get('/api/custom-orders/$id');
    return CustomOrder.fromJson(Map<String, dynamic>.from(body as Map));
  }

  Future<CustomOrder> create({
    required String productType,
    required String description,
    required int quantity,
    required String preferredDate,
    List<PickedImage> images = const [],
  }) async {
    final body = await _client.postMultipart(
      '/api/custom-orders',
      fields: {
        'productType': productType.trim(),
        'description': description.trim(),
        'quantity': quantity.toString(),
        'preferredDate': preferredDate,
      },
      files: [
        for (final i in images)
          http.MultipartFile.fromBytes('images', i.bytes, filename: i.name),
      ],
    );
    return CustomOrder.fromJson(Map<String, dynamic>.from(body as Map));
  }
}
