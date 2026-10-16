#include "FDMinimap.h"

#include "Engine/Texture2D.h"
#include "FDBikePawn.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Misc/App.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"

namespace
{
	constexpr int32 CircleSegments = 72;
	constexpr float BorderPx = 3.f;
	constexpr float ZoomResponse = 1.5f;  // 映す範囲の追従速度 (1/秒)

	const FColor BorderColor(235, 235, 235, 230);
	const FColor NoMapColor(40, 60, 45, 220);
	const FColor BikeColor(255, 70, 30);
	const FColor BikeOutlineColor(20, 20, 20);
	const FColor MarkerColor(255, 190, 0);
	const FColor ParkedBikeColor(40, 170, 255);

	/** 中心 Center、半径 Radius の円を三角形の扇で塗る。UV は位置から UvOf で決める */
	template <typename FUvOf>
	void AddDisc(TArray<FSlateVertex>& Verts, TArray<SlateIndex>& Indices, const FSlateRenderTransform& Transform,
	             const FVector2f& Center, float Radius, const FColor& Color, FUvOf UvOf)
	{
		const SlateIndex First = Verts.Num();
		Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Transform, Center, UvOf(FVector2f::ZeroVector), Color));
		for (int32 i = 0; i < CircleSegments; ++i)
		{
			const float A = UE_TWO_PI * i / CircleSegments;
			const FVector2f Offset(FMath::Cos(A) * Radius, FMath::Sin(A) * Radius);
			Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Transform, Center + Offset, UvOf(Offset), Color));
		}
		for (int32 i = 0; i < CircleSegments; ++i)
		{
			Indices.Add(First);
			Indices.Add(First + 1 + i);
			Indices.Add(First + 1 + (i + 1) % CircleSegments);
		}
	}

	void AddPolygon(TArray<FSlateVertex>& Verts, TArray<SlateIndex>& Indices, const FSlateRenderTransform& Transform,
	                const FVector2f& Center, TConstArrayView<FVector2f> Points, float Scale, const FColor& Color)
	{
		// 凸でない形 (矢印) も扱えるよう、中心からの扇にする
		const SlateIndex First = Verts.Num();
		Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Transform, Center, FVector2f(0.5f, 0.5f), Color));
		for (const FVector2f& P : Points)
		{
			Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Transform, Center + P * Scale, FVector2f(0.5f, 0.5f), Color));
		}
		for (int32 i = 0; i < Points.Num(); ++i)
		{
			Indices.Add(First);
			Indices.Add(First + 1 + i);
			Indices.Add(First + 1 + (i + 1) % Points.Num());
		}
	}
}

void SFDMinimap::Construct(const FArguments& InArgs)
{
	Player = InArgs._Player;
	ParkedBike = InArgs._ParkedBike;
	MapMin = InArgs._MapMin;
	MapMax = InArgs._MapMax;
	GridRotationDeg = InArgs._GridRotationDeg;
	Markers = InArgs._Markers;
	Diameter = InArgs._Diameter;
	RadiusSlowM = InArgs._RadiusSlowM;
	RadiusFastM = InArgs._RadiusFastM;
	RadiusM = RadiusSlowM;

	bHasMap = InArgs._MapTexture != nullptr && MapMax.X > MapMin.X && MapMax.Y > MapMin.Y;
	if (bHasMap)
	{
		MapBrush.SetResourceObject(InArgs._MapTexture);
		MapBrush.ImageSize = FVector2D(InArgs._MapTexture->GetSizeX(), InArgs._MapTexture->GetSizeY());
	}
	// 毎フレーム描き直す (プレイヤーが動くので、前のフレームの絵は使い回せない)
	ForceVolatile(true);
}

FVector2D SFDMinimap::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(Diameter, Diameter);
}

int32 SFDMinimap::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
                          FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle,
                          bool bParentEnabled) const
{
	const APawn* Pawn = Player.Get();
	if (!Pawn)
	{
		return LayerId;
	}

	// 速いほど先まで見えるように広く映す (バイクは自前で動かしているので、速度はバイクに聞く)
	const AFDBikePawn* Bike = Cast<AFDBikePawn>(Pawn);
	const float SpeedKmh = Bike ? Bike->GetSpeedKmh() : static_cast<float>(Pawn->GetVelocity().Size2D() * 0.036);
	const float SpeedT = FMath::Clamp(SpeedKmh / 60.f, 0.f, 1.f);
	RadiusM = FMath::FInterpTo(RadiusM, FMath::Lerp(RadiusSlowM, RadiusFastM, SpeedT), FApp::GetDeltaTime(), ZoomResponse);

	const FVector2f Size = FVector2f(AllottedGeometry.GetLocalSize());
	const FVector2f Center = Size * 0.5f;
	const float R = FMath::Min(Size.X, Size.Y) * 0.5f - BorderPx;
	const FSlateRenderTransform& Transform = AllottedGeometry.GetAccumulatedRenderTransform();

	// 画面の右・上 (Slate は下が +Y) に対応する UE の水平の向き。進む向きが上
	const FVector Location = Pawn->GetActorLocation();
	const float Yaw = FMath::DegreesToRadians(Pawn->GetActorRotation().Yaw);
	const FVector2D Forward(FMath::Cos(Yaw), FMath::Sin(Yaw));
	const FVector2D Right(-FMath::Sin(Yaw), FMath::Cos(Yaw));
	const double CmPerPx = RadiusM * 100.0 / R;

	auto WorldToScreen = [&](const FVector2D& World)
	{
		const FVector2D D = (World - FVector2D(Location)) / CmPerPx;
		return FVector2f(FVector2D(D | Right, -(D | Forward)));
	};
	const FVector2D MapSize = MapMax - MapMin;
	auto ScreenToUv = [&](const FVector2f& Offset)
	{
		const FVector2D World = FVector2D(Location) + (Right * Offset.X - Forward * Offset.Y) * CmPerPx;
		return FVector2f((World - MapMin) / MapSize);
	};
	auto NoUv = [](const FVector2f&) { return FVector2f(0.5f, 0.5f); };

	const FSlateBrush* White = FCoreStyle::Get().GetBrush(TEXT("GenericWhiteBox"));
	FSlateRenderer* Renderer = FSlateApplication::Get().GetRenderer();
	const FSlateResourceHandle WhiteHandle = Renderer->GetResourceHandle(*White);

	TArray<FSlateVertex> Verts;
	TArray<SlateIndex> Indices;

	// 縁取り
	AddDisc(Verts, Indices, Transform, Center, R + BorderPx, BorderColor, NoUv);
	FSlateDrawElement::MakeCustomVerts(OutDrawElements, LayerId, WhiteHandle, Verts, Indices, nullptr, 0, 0);
	Verts.Reset();
	Indices.Reset();

	// 地図
	if (bHasMap)
	{
		AddDisc(Verts, Indices, Transform, Center, R, FColor::White, ScreenToUv);
		FSlateDrawElement::MakeCustomVerts(OutDrawElements, LayerId + 1, Renderer->GetResourceHandle(MapBrush), Verts, Indices, nullptr, 0, 0);
	}
	else
	{
		AddDisc(Verts, Indices, Transform, Center, R, NoMapColor, NoUv);
		FSlateDrawElement::MakeCustomVerts(OutDrawElements, LayerId + 1, WhiteHandle, Verts, Indices, nullptr, 0, 0);
	}
	Verts.Reset();
	Indices.Reset();

	// ファストトラベルの行き先 (円の中に入るものだけ)
	static const FVector2f Diamond[] = {{0.f, -1.f}, {1.f, 0.f}, {0.f, 1.f}, {-1.f, 0.f}};
	for (const FVector2D& Marker : Markers)
	{
		const FVector2f P = WorldToScreen(Marker);
		if (P.Size() < R - 7.f)
		{
			AddPolygon(Verts, Indices, Transform, Center + P, Diamond, 7.f, BikeOutlineColor);
			AddPolygon(Verts, Indices, Transform, Center + P, Diamond, 5.f, MarkerColor);
		}
	}

	// 止めてあるバイク (円の外なら縁に寄せて、どちらにあるかわかるように)
	if (const AActor* Parked = ParkedBike.Get(); Parked && Parked != Pawn)
	{
		FVector2f P = WorldToScreen(FVector2D(Parked->GetActorLocation()));
		P = P.GetClampedToMaxSize(R - 9.f);
		static const FVector2f Square[] = {{-1.f, -1.f}, {1.f, -1.f}, {1.f, 1.f}, {-1.f, 1.f}};
		AddPolygon(Verts, Indices, Transform, Center + P, Square, 7.f, BikeOutlineColor);
		AddPolygon(Verts, Indices, Transform, Center + P, Square, 5.f, ParkedBikeColor);
	}

	// プレイヤー (中心で上を向いた矢印)
	static const FVector2f Arrow[] = {{0.f, -1.f}, {0.7f, 0.8f}, {0.f, 0.4f}, {-0.7f, 0.8f}};
	AddPolygon(Verts, Indices, Transform, Center + FVector2f(0.f, 1.f), Arrow, 13.f, BikeOutlineColor);
	AddPolygon(Verts, Indices, Transform, Center, Arrow, 10.f, BikeColor);
	FSlateDrawElement::MakeCustomVerts(OutDrawElements, LayerId + 2, WhiteHandle, Verts, Indices, nullptr, 0, 0);

	// 北の印を縁の上に (升目を回していなければ UE の -Y、回しているときは (sin, -cos) の向き)
	const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle("Bold", 13);
	const FString North = TEXT("N");
	const FVector2f TextSize = FVector2f(Renderer->GetFontMeasureService()->Measure(North, Font));
	const double GridRot = FMath::DegreesToRadians(static_cast<double>(GridRotationDeg));
	const FVector2f NorthDir = WorldToScreen(FVector2D(Location) + FVector2D(FMath::Sin(GridRot), -FMath::Cos(GridRot)) * CmPerPx).GetSafeNormal();
	const FVector2f NorthPos = Center + NorthDir * (R - TextSize.Y * 0.5f - 2.f) - TextSize * 0.5f;
	FSlateDrawElement::MakeText(OutDrawElements, LayerId + 3,
	                            AllottedGeometry.ToPaintGeometry(TextSize, FSlateLayoutTransform(NorthPos + FVector2f(1.f, 1.f))),
	                            North, Font, ESlateDrawEffect::None, FLinearColor::Black);
	FSlateDrawElement::MakeText(OutDrawElements, LayerId + 4, AllottedGeometry.ToPaintGeometry(TextSize, FSlateLayoutTransform(NorthPos)),
	                            North, Font, ESlateDrawEffect::None, FLinearColor::White);

	return LayerId + 4;
}
