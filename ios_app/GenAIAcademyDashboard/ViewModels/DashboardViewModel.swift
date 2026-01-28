//
//  DashboardViewModel.swift
//  GenAIAcademyDashboard
//
//  ViewModel for dashboard screen
//

import Foundation
import SwiftUI

@MainActor
class DashboardViewModel: ObservableObject {
    @Published var summary: DashboardSummary?
    @Published var charts: DashboardCharts?
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var selectedPeriod: Period = .thirtyDays
    
    enum Period: String, CaseIterable {
        case sevenDays = "7d"
        case thirtyDays = "30d"
        case ninetyDays = "90d"
        
        var displayName: String {
            switch self {
            case .sevenDays: return "Last 7 Days"
            case .thirtyDays: return "Last 30 Days"
            case .ninetyDays: return "Last 90 Days"
            }
        }
    }
    
    private let networkManager = NetworkManager.shared
    
    /// Load dashboard summary data
    func loadSummary() async {
        do {
            let endpoint = "\(Constants.dashboardSummaryEndpoint)?period=\(selectedPeriod.rawValue)"
            summary = try await networkManager.request(
                endpoint: endpoint,
                responseType: DashboardSummary.self
            )
            errorMessage = nil
        } catch let error as NetworkError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = "Failed to load dashboard data"
        }
    }
    
    /// Load dashboard charts data
    func loadCharts() async {
        do {
            let endpoint = "\(Constants.dashboardChartsEndpoint)?period=\(selectedPeriod.rawValue)"
            charts = try await networkManager.request(
                endpoint: endpoint,
                responseType: DashboardCharts.self
            )
        } catch {
            // Charts are optional, don't show error if they fail
            print("Failed to load charts: \(error)")
        }
    }
    
    /// Load all dashboard data
    func loadDashboardData() async {
        isLoading = true
        errorMessage = nil
        
        await withTaskGroup(of: Void.self) { group in
            group.addTask { await self.loadSummary() }
            group.addTask { await self.loadCharts() }
        }
        
        isLoading = false
    }
    
    /// Refresh dashboard data
    func refresh() async {
        await loadDashboardData()
    }
    
    /// Change time period and reload data
    func changePeriod(_ period: Period) async {
        selectedPeriod = period
        await loadDashboardData()
    }
}
