import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/app_failure.dart';
import '../../../core/validators.dart';
import '../../auth/state/session_provider.dart';
import '../../payment/data/malaysia_payments.dart';
import '../data/checkout_models.dart';
import '../data/checkout_repository.dart';

/// Step indexes: 0 cart review, 1 delivery, 2 payment method, 3 confirmation.
const checkoutStepTitles = [
  'Cart review',
  'Delivery details',
  'Payment method',
  'Confirmation',
];

const couldNotProcessMessage =
    'We could not process your request. Your order and stock were not changed. Please try again.';

/// Per-field validation of the delivery step (Req 12.3). Keys are field names.
Map<String, String> validateDelivery(DeliveryForm f) {
  final errors = <String, String?>{
    'name': validateName(f.name),
    'phone': validateMalaysianPhone(f.phone),
    'email': validateEmail(f.email),
    'address': validateAddress(f.address),
    'postcode': validatePostcode(f.postcode),
    'state': validateState(f.state),
    'notes': validateNotes(f.notes),
  };
  return {
    for (final e in errors.entries)
      if (e.value != null) e.key: e.value!,
  };
}

/// Idempotency key of 10 to 80 characters (Req 12.6).
String newIdempotencyKey([Random? random]) {
  final r = random ?? Random.secure();
  final hex = List.generate(16, (_) => r.nextInt(16).toRadixString(16)).join();
  return 'chk-${DateTime.now().microsecondsSinceEpoch}-$hex';
}

class CheckoutState {
  const CheckoutState({
    this.step = 0,
    this.delivery = const DeliveryForm(),
    this.errors = const {},
    this.method,
    this.channel,
    this.providerId,
    this.outcome,
    this.idempotencyKey,
    this.submitting = false,
    this.error,
    this.shortages = const [],
    this.prefilled = false,
    this.formVersion = 0,
  });

  final int step;
  final DeliveryForm delivery;
  final Map<String, String> errors;
  final String? method;

  /// Checkout channel (FPX, e-wallet, DuitNow QR, card or COD).
  final PaymentChannel? channel;

  /// Chosen bank or e-wallet id, kept on this device.
  final String? providerId;

  /// Result reported by the payment gateway screen.
  final String? outcome;

  /// Created once per attempt and reused until the order is placed.
  final String? idempotencyKey;
  final bool submitting;
  final String? error;
  final List<StockShortage> shortages;
  final bool prefilled;

  /// Bumped when the form is replaced from outside (address prefill).
  final int formVersion;

  /// A method is chosen, and a bank or wallet when the channel needs one.
  bool get paymentChosen =>
      method != null && (channel?.needsProvider != true || providerId != null);

  CheckoutState copyWith({
    int? step,
    DeliveryForm? delivery,
    Map<String, String>? errors,
    String? method,
    PaymentChannel? channel,
    String? providerId,
    bool clearProvider = false,
    String? outcome,
    bool clearOutcome = false,
    String? idempotencyKey,
    bool? submitting,
    String? error,
    bool clearError = false,
    List<StockShortage>? shortages,
    bool? prefilled,
    int? formVersion,
  }) =>
      CheckoutState(
        step: step ?? this.step,
        delivery: delivery ?? this.delivery,
        errors: errors ?? this.errors,
        method: method ?? this.method,
        channel: channel ?? this.channel,
        providerId: clearProvider ? null : (providerId ?? this.providerId),
        outcome: clearOutcome ? null : (outcome ?? this.outcome),
        idempotencyKey: idempotencyKey ?? this.idempotencyKey,
        submitting: submitting ?? this.submitting,
        error: clearError ? null : (error ?? this.error),
        shortages: shortages ?? this.shortages,
        prefilled: prefilled ?? this.prefilled,
        formVersion: formVersion ?? this.formVersion,
      );
}

class CheckoutFlow extends Notifier<CheckoutState> {
  @override
  CheckoutState build() => const CheckoutState();

  /// Prefills from the default address once, when the form is still blank.
  void prefill(SavedAddress? address) {
    if (state.prefilled) return;
    final session = ref.read(sessionProvider);
    final email = session is SessionSignedIn ? session.user.email : '';
    final blank = state.delivery.toJson().values.every((v) => v == '');
    if (!blank) {
      state = state.copyWith(prefilled: true);
      return;
    }
    final form = address?.toForm(email: email) ?? DeliveryForm(email: email);
    state = state.copyWith(
        delivery: form, prefilled: true, formVersion: state.formVersion + 1);
  }

  void updateDelivery(DeliveryForm form) =>
      state = state.copyWith(delivery: form);

  void goTo(int step) =>
      state = state.copyWith(step: step, clearError: true, shortages: const []);

  /// Delivery to payment: blocks and keeps values when a field is invalid.
  bool continueFromDelivery() {
    final errors = validateDelivery(state.delivery);
    state = state.copyWith(errors: errors, clearError: true);
    if (errors.isNotEmpty) return false;
    state = state.copyWith(step: 2);
    return true;
  }

  void chooseMethod(String method) => state = state.copyWith(
      method: method,
      clearOutcome: !methodNeedsOutcome(method),
      clearError: true);

  /// Picks a checkout channel; switching channel clears the bank or wallet.
  void chooseChannel(PaymentChannel channel, {String? providerId}) =>
      state = state.copyWith(
        method: channel.method,
        channel: channel,
        providerId: providerId,
        clearProvider: providerId == null && channel != state.channel,
        clearOutcome: true,
        clearError: true,
      );

  void chooseOutcome(String outcome) =>
      state = state.copyWith(outcome: outcome, clearError: true);

  bool continueFromPayment() {
    if (!state.paymentChosen) {
      state = state.copyWith(
          error: state.method == null
              ? 'Choose a payment method.'
              : state.channel == PaymentChannel.fpx
                  ? 'Choose your bank.'
                  : 'Choose your e-wallet.');
      return false;
    }
    state = state.copyWith(step: 3, clearError: true);
    return true;
  }

  /// Places the order. Returns the order id on success, otherwise null with
  /// the error and the entered values kept (Req 12.3, 13.13).
  Future<String?> submit() async {
    if (state.submitting) return null;
    final errors = validateDelivery(state.delivery);
    if (errors.isNotEmpty) {
      state = state.copyWith(errors: errors, step: 1);
      return null;
    }
    if (!state.paymentChosen) {
      state = state.copyWith(step: 2, error: 'Choose a payment method.');
      return null;
    }
    if (methodNeedsOutcome(state.method!) && state.outcome == null) {
      state = state.copyWith(error: 'Complete the payment to place your order.');
      return null;
    }
    final key = state.idempotencyKey ?? newIdempotencyKey();
    state = state.copyWith(
        idempotencyKey: key,
        submitting: true,
        clearError: true,
        shortages: const []);
    try {
      final order = await ref.read(checkoutRepositoryProvider).placeOrder(
            idempotencyKey: key,
            delivery: state.delivery,
            method: state.method!,
            outcome: state.outcome,
          );
      ref.invalidate(checkoutCartProvider);
      state = state.copyWith(submitting: false, clearError: true);
      return order.id;
    } on ValidationFailure catch (e) {
      final fields = <String, String>{};
      e.fields.forEach((k, v) => fields[k.replaceFirst('delivery.', '')] = v);
      final deliveryErrors = {
        for (final k in const [
          'name',
          'phone',
          'email',
          'address',
          'postcode',
          'state',
          'notes'
        ])
          if (fields.containsKey(k)) k: fields[k]!,
      };
      state = state.copyWith(
          submitting: false,
          errors: deliveryErrors,
          step: deliveryErrors.isNotEmpty ? 1 : state.step,
          error: deliveryErrors.isEmpty ? e.message : null);
    } on ConflictFailure catch (e) {
      final shortages = [
        for (final d in e.details)
          if (d is Map) StockShortage.fromJson(Map<String, dynamic>.from(d)),
      ];
      state = state.copyWith(
          submitting: false,
          shortages: shortages,
          error: shortages.isEmpty
              ? e.message
              : 'Some items are short on stock. Update your cart and try again.');
    } on ServerFailure catch (e) {
      // 4xx such as an empty cart (400) carries a usable message.
      state = state.copyWith(
          submitting: false,
          error: e.statusCode < 500 ? e.message : couldNotProcessMessage);
    } on AppFailure {
      state = state.copyWith(submitting: false, error: couldNotProcessMessage);
    } catch (_) {
      state = state.copyWith(submitting: false, error: couldNotProcessMessage);
    }
    return null;
  }
}

final checkoutFlowProvider =
    NotifierProvider.autoDispose<CheckoutFlow, CheckoutState>(CheckoutFlow.new);
