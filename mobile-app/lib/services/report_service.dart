import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'dart:convert';
import 'package:mime/mime.dart';

// ── Data models ─────────────────────────────────────────────────────────────

class TrackMessage {
  final String id;
  final String sender; // 'analyst' or 'reporter'
  final String message;
  final String createdAt;

  TrackMessage({
    required this.id,
    required this.sender,
    required this.message,
    required this.createdAt,
  });

  factory TrackMessage.fromJson(Map<String, dynamic> j) => TrackMessage(
        id: j['id'] ?? '',
        sender: j['sender'] ?? '',
        message: j['message'] ?? '',
        createdAt: j['created_at'] ?? '',
      );
}

class TrackResponse {
  final String reportId;
  final String status;
  final String? userCategory;
  final String? category;
  final String submittedAt;
  final String? urgencyLevel;
  final List<TrackMessage> messages;
  final int unreadFromAnalyst;

  TrackResponse({
    required this.reportId,
    required this.status,
    this.userCategory,
    this.category,
    required this.submittedAt,
    this.urgencyLevel,
    required this.messages,
    required this.unreadFromAnalyst,
  });

  factory TrackResponse.fromJson(Map<String, dynamic> j) => TrackResponse(
        reportId: j['report_id'] ?? '',
        status: j['status'] ?? 'pending',
        userCategory: j['user_category'],
        category: j['category'],
        submittedAt: j['submitted_at'] ?? '',
        urgencyLevel: j['urgency_level'],
        messages: (j['messages'] as List<dynamic>? ?? [])
            .map((m) => TrackMessage.fromJson(m as Map<String, dynamic>))
            .toList(),
        unreadFromAnalyst: j['unread_from_analyst'] ?? 0,
      );
}

// ── Service ─────────────────────────────────────────────────────────────────

/// Service for submitting and tracking anonymous reports.
///
/// PRIVACY: This service deliberately avoids any device fingerprinting.
/// No device ID, no app ID headers are sent.
class ReportService extends ChangeNotifier {
  static const String _baseUrl = String.fromEnvironment('API_URL',
      defaultValue: 'http://192.168.100.78/api/v1');

  bool _isLoading = false;
  String? _lastError;
  String? _lastReportId;
  String? _lastTrackingCode;

  bool get isLoading => _isLoading;
  String? get lastError => _lastError;
  String? get lastReportId => _lastReportId;
  String? get lastTrackingCode => _lastTrackingCode;

  /// Submit an anonymous report.
  /// Returns the report ID on success.
  Future<String> submitReport({
    String? textContent,
    String? userCategory,
    String? locationHint,
    String? audioPath,
    String? imagePath,
  }) async {
    _isLoading = true;
    _lastError = null;
    _lastTrackingCode = null;
    notifyListeners();

    try {
      final uri = Uri.parse('$_baseUrl/reports/submit');
      final request = http.MultipartRequest('POST', uri);

      // PRIVACY: No identifying headers
      if (textContent != null && textContent.isNotEmpty) {
        request.fields['text_content'] = textContent;
      }
      if (userCategory != null) {
        request.fields['user_category'] = userCategory;
      }
      if (locationHint != null && locationHint.isNotEmpty) {
        request.fields['location_hint'] = locationHint;
      }

      if (audioPath != null) {
        final audioFile = File(audioPath);
        if (await audioFile.exists()) {
          request.files.add(
            await http.MultipartFile.fromPath(
              'audio_file',
              audioPath,
              contentType: MediaType('audio', 'wav'),
              filename: 'audio.wav',
            ),
          );
        }
      }

      if (imagePath != null) {
        final imageFile = File(imagePath);
        if (await imageFile.exists()) {
          final mimeType = lookupMimeType(imagePath) ?? 'image/jpeg';
          final parts = mimeType.split('/');
          request.files.add(
            await http.MultipartFile.fromPath(
              'image_file',
              imagePath,
              contentType: MediaType(parts[0], parts[1]),
              filename: 'image.${parts[1]}',
            ),
          );
        }
      }

      final streamedResponse = await request.send().timeout(
            const Duration(seconds: 30),
            onTimeout: () =>
                throw Exception('Connection timed out. Please try again.'),
          );

      final response = await http.Response.fromStream(streamedResponse);

      if (response.statusCode == 202) {
        final data = jsonDecode(response.body);
        final reportId = data['report_id'] as String;
        _lastReportId = reportId;
        _lastTrackingCode = data['tracking_code'] as String?;
        return reportId;
      } else if (response.statusCode == 429) {
        throw Exception(
            'Service temporarily at capacity. Please try again in a few minutes.');
      } else if (response.statusCode >= 500) {
        throw Exception('Server error. Please try again later.');
      } else {
        final data = jsonDecode(response.body);
        throw Exception(data['detail'] ?? 'Submission failed');
      }
    } on SocketException {
      throw Exception(
          'No internet connection. Please check your network and try again.');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Track a report using the anonymous tracking code.
  Future<TrackResponse> trackReport(String trackingCode) async {
    final uri = Uri.parse('$_baseUrl/reports/track');
    final request = http.MultipartRequest('POST', uri);
    request.fields['tracking_code'] = trackingCode.trim().toUpperCase();

    try {
      final streamed = await request.send().timeout(
            const Duration(seconds: 20),
            onTimeout: () => throw Exception('Connection timed out.'),
          );
      final response = await http.Response.fromStream(streamed);

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        return TrackResponse.fromJson(data);
      } else if (response.statusCode == 404) {
        throw Exception('Tracking code not found');
      } else {
        final data = jsonDecode(response.body);
        throw Exception(data['detail'] ?? 'Tracking failed');
      }
    } on SocketException {
      throw Exception('No internet connection.');
    }
  }

  /// Reporter sends a message using their tracking code.
  Future<void> sendReporterMessage(String trackingCode, String message) async {
    final uri = Uri.parse('$_baseUrl/reports/track/message');
    final request = http.MultipartRequest('POST', uri);
    request.fields['tracking_code'] = trackingCode.trim().toUpperCase();
    request.fields['message'] = message.trim();

    try {
      final streamed = await request.send().timeout(
            const Duration(seconds: 20),
            onTimeout: () => throw Exception('Connection timed out.'),
          );
      final response = await http.Response.fromStream(streamed);

      if (response.statusCode != 201) {
        final data = jsonDecode(response.body);
        throw Exception(data['detail'] ?? 'Failed to send message');
      }
    } on SocketException {
      throw Exception('No internet connection.');
    }
  }
}
