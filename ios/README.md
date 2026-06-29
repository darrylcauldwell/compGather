# EquiCalendar iOS

Native SwiftUI companion app for the EquiCalendar backend. Browse upcoming
equestrian events, filter by discipline and distance, see event detail with a
map, add to your calendar, and save favourites offline.

## Stack
- SwiftUI + `@Observable` MVVM, async/await, iOS 26 **Liquid Glass**
- **SwiftData** for offline favourites
- Reads the backend JSON API (`/api/competitions`, `/api/geocode/reverse`)
- Swift Testing for unit tests

## Build & run
The Xcode project is generated from `project.yml` with
[xcodegen](https://github.com/yonyz/xcodegen) (it is git-ignored):

```sh
cd ios
xcodegen generate
xcodebuild -project EquiCalendar.xcodeproj -scheme EquiCalendar \
  -destination 'generic/platform=iOS Simulator' build
```

Open `EquiCalendar.xcodeproj` in Xcode 26 to run in the simulator or on device.

## Configuration
Set the backend base URL in `EquiCalendar/AppConfig.swift`
(`AppConfig.baseURL`). It defaults to the production instance; use
`http://localhost:8001` for local development against the Docker stack.

## Layout
```
EquiCalendar/
  EquiCalendarApp.swift     @main + SwiftData container
  AppConfig.swift           backend base URL
  Models/                   Competition (DTO), Favourite (@Model)
  Services/                 APIClient, LocationManager, CalendarService
  ViewModels/               EventsViewModel (@Observable)
  Views/                    AppTypography, Root/Events/Detail/Favourites + components
EquiCalendarTests/          Swift Testing
```
