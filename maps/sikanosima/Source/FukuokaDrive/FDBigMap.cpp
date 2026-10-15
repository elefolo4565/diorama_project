#include "FDBigMap.h"

#include "Engine/Texture2D.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/Pawn.h"
#include "HAL/PlatformTime.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"

namespace
{
	constexpr double MaxZoom = 40.0;
	constexpr float PickRadiusPx = 18.f;   // 行き先の ◆ をクリックしたとみなす距離
	constexpr float DragStartPx = 5.f;     // これより動かしたらクリックではなくドラッグ
	constexpr double MessageSeconds = 2.5;

	const FLinearColor BigMapBackColor(0.03f, 0.05f, 0.07f, 0.92f);
	const FColor BigMapFrameColor(235, 235, 235, 200);
	const FColor BigMapPlayerColor(255, 70, 30);
	const FColor BigMapOutlineColor(20, 20, 20);
	const FColor BigMapPointColor(255, 190, 0);
	const FColor BigMapPointHoverColor(255, 245, 140);
	const FColor BigMapParkedColor(40, 170, 255);
	const FColor BigMapCursorColor(255, 255, 255, 220);

	/** 中心からの扇で多角形を塗る (凸でない矢印も塗れる)。Points は Axis X/Y で回してから Scale 倍 */
	void BigMapPolygon(TArray<FSlateVertex>& Verts, TArray<SlateIndex>& Indices, const FSlateRenderTransform& Transform,
	                   const FVector2f& Center, TConstArrayView<FVector2f> Points, float Scale, const FColor& Color,
	                   const FVector2f& AxisX = FVector2f(1.f, 0.f), const FVector2f& AxisY = FVector2f(0.f, 1.f))
	{
		const SlateIndex First = Verts.Num();
		Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Transform, Center, FVector2f(0.5f, 0.5f), Color));
		for (const FVector2f& P : Points)
		{
			const FVector2f R = (AxisX * P.X + AxisY * P.Y) * Scale;
			Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Transform, Center + R, FVector2f(0.5f, 0.5f), Color));
		}
		for (int32 i = 0; i < Points.Num(); ++i)
		{
			Indices.Add(First);
			Indices.Add(First + 1 + i);
			Indices.Add(First + 1 + (i + 1) % Points.Num());
		}
	}

	/** 線 (細い四角) */
	void BigMapLine(TArray<FSlateVertex>& Verts, TArray<SlateIndex>& Indices, const FSlateRenderTransform& Transform,
	                const FVector2f& A, const FVector2f& B, float Width, const FColor& Color)
	{
		const FVector2f Dir = (B - A).GetSafeNormal();
		const FVector2f N = FVector2f(-Dir.Y, Dir.X) * (Width * 0.5f);
		const SlateIndex First = Verts.Num();
		for (const FVector2f& P : {A + N, B + N, B - N, A - N})
		{
			Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Transform, P, FVector2f(0.5f, 0.5f), Color));
		}
		Indices.Append({SlateIndex(First), SlateIndex(First + 1), SlateIndex(First + 2), SlateIndex(First), SlateIndex(First + 2), SlateIndex(First + 3)});
	}

	/** 影つきの文字 */
	void BigMapText(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FString& Text,
	                const FSlateFontInfo& Font, const FVector2f& TopLeft, const FLinearColor& Color)
	{
		const FVector2f Size = FVector2f(FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Text, Font));
		FSlateDrawElement::MakeText(OutDrawElements, Layer, Geometry.ToPaintGeometry(Size, FSlateLayoutTransform(TopLeft + FVector2f(1.5f, 1.5f))),
		                            Text, Font, ESlateDrawEffect::None, FLinearColor(0.f, 0.f, 0.f, 0.9f));
		FSlateDrawElement::MakeText(OutDrawElements, Layer + 1, Geometry.ToPaintGeometry(Size, FSlateLayoutTransform(TopLeft)),
		                            Text, Font, ESlateDrawEffect::None, Color);
	}

	FVector2f BigMapMeasure(const FString& Text, const FSlateFontInfo& Font)
	{
		return FVector2f(FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(Text, Font));
	}
}

void SFDBigMap::Construct(const FArguments& InArgs)
{
	Player = InArgs._Player;
	ParkedBike = InArgs._ParkedBike;
	MapMin = InArgs._MapMin;
	MapMax = InArgs._MapMax;
	GridRotationDeg = InArgs._GridRotationDeg;
	Points = InArgs._Points;
	OnPick = InArgs._OnPick;

	bHasMap = InArgs._MapTexture != nullptr && MapMax.X > MapMin.X && MapMax.Y > MapMin.Y;
	if (bHasMap)
	{
		MapBrush.SetResourceObject(InArgs._MapTexture);
		MapBrush.ImageSize = FVector2D(InArgs._MapTexture->GetSizeX(), InArgs._MapTexture->GetSizeY());
	}
	else
	{
		// 地図の画像が無ければ、行き先とプレイヤーが収まる範囲を無地で出す
		FBox2D Box(ForceInit);
		for (const FPoint& Point : Points)
		{
			Box += Point.Location;
		}
		if (const APawn* Pawn = Player.Get())
		{
			Box += FVector2D(Pawn->GetActorLocation());
		}
		if (!Box.bIsValid)
		{
			Box = FBox2D(FVector2D(-100000.0), FVector2D(100000.0));
		}
		Box = Box.ExpandBy(100000.0);
		MapMin = Box.Min;
		MapMax = Box.Max;
	}
	ViewCenter = (MapMin + MapMax) * 0.5;
	// プレイヤーが動くので毎フレーム描き直す
	ForceVolatile(true);
}

FVector2D SFDBigMap::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(600.f, 600.f);
}

double SFDBigMap::CmPerPx(const FVector2f& Size) const
{
	const FVector2D MapSize = MapMax - MapMin;
	const double Fit = FMath::Max(MapSize.X / FMath::Max(Size.X, 1.f), MapSize.Y / FMath::Max(Size.Y, 1.f));
	return Fit / Zoom;
}

FVector2f SFDBigMap::WorldToLocal(const FVector2D& World, const FVector2f& Size) const
{
	return Size * 0.5f + FVector2f((World - ViewCenter) / CmPerPx(Size));
}

FVector2D SFDBigMap::LocalToWorld(const FVector2f& Local, const FVector2f& Size) const
{
	return ViewCenter + FVector2D(Local - Size * 0.5f) * CmPerPx(Size);
}

int32 SFDBigMap::FindPoint(const FVector2f& Local, const FVector2f& Size) const
{
	int32 Best = INDEX_NONE;
	float BestDist = PickRadiusPx;
	for (int32 i = 0; i < Points.Num(); ++i)
	{
		const float Dist = FVector2f::Distance(WorldToLocal(Points[i].Location, Size), Local);
		if (Dist < BestDist)
		{
			Best = i;
			BestDist = Dist;
		}
	}
	return Best;
}

void SFDBigMap::ClampView()
{
	Zoom = FMath::Clamp(Zoom, 1.0, MaxZoom);
	ViewCenter.X = FMath::Clamp(ViewCenter.X, MapMin.X, MapMax.X);
	ViewCenter.Y = FMath::Clamp(ViewCenter.Y, MapMin.Y, MapMax.Y);
}

// ---------------------------------------------------------------- マウス

FReply SFDBigMap::OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	if (MouseEvent.GetEffectingButton() != EKeys::LeftMouseButton)
	{
		return FReply::Unhandled();
	}
	bPressed = true;
	bDragged = false;
	PressLocal = FVector2f(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	PressViewCenter = ViewCenter;
	return FReply::Handled().CaptureMouse(SharedThis(this));
}

FReply SFDBigMap::OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	const FVector2f Local = FVector2f(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	HoverLocal = Local;
	if (bPressed)
	{
		if (!bDragged && FVector2f::Distance(Local, PressLocal) > DragStartPx)
		{
			bDragged = true;
		}
		if (bDragged)
		{
			const FVector2f Size = FVector2f(MyGeometry.GetLocalSize());
			ViewCenter = PressViewCenter - FVector2D(Local - PressLocal) * CmPerPx(Size);
			ClampView();
		}
	}
	return FReply::Handled();
}

FReply SFDBigMap::OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	if (MouseEvent.GetEffectingButton() != EKeys::LeftMouseButton || !bPressed)
	{
		return FReply::Unhandled();
	}
	bPressed = false;
	FReply Reply = FReply::Handled().ReleaseMouseCapture();
	if (bDragged)
	{
		return Reply;
	}

	const FVector2f Size = FVector2f(MyGeometry.GetLocalSize());
	const FVector2f Local = FVector2f(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	const int32 PointIndex = FindPoint(Local, Size);
	const FVector2D World = PointIndex != INDEX_NONE ? Points[PointIndex].Location : LocalToWorld(Local, Size);
	FString Error;
	if (PointIndex == INDEX_NONE && (World.X < MapMin.X || World.X > MapMax.X || World.Y < MapMin.Y || World.Y > MapMax.Y))
	{
		Error = TEXT("地図の外には移動できません");
	}
	else if (OnPick.IsBound())
	{
		// 移れたときはこの地図ごと閉じられる (この後でメンバーに触らない)
		Error = OnPick.Execute(World, PointIndex);
		if (Error.IsEmpty())
		{
			return Reply;
		}
	}
	Message = Error;
	MessageUntil = FPlatformTime::Seconds() + MessageSeconds;
	return Reply;
}

FReply SFDBigMap::OnMouseWheel(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	// カーソルの下の地点を動かさずに拡大・縮小する
	const FVector2f Size = FVector2f(MyGeometry.GetLocalSize());
	const FVector2f Local = FVector2f(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	const FVector2D Before = LocalToWorld(Local, Size);
	Zoom *= MouseEvent.GetWheelDelta() > 0.f ? 1.25 : 0.8;
	Zoom = FMath::Clamp(Zoom, 1.0, MaxZoom);
	ViewCenter += Before - LocalToWorld(Local, Size);
	ClampView();
	return FReply::Handled();
}

void SFDBigMap::OnMouseLeave(const FPointerEvent& MouseEvent)
{
	HoverLocal.Reset();
}

// ---------------------------------------------------------------- 描く

int32 SFDBigMap::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
                         FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle,
                         bool bParentEnabled) const
{
	const FVector2f Size = FVector2f(AllottedGeometry.GetLocalSize());
	const FSlateRenderTransform& Transform = AllottedGeometry.GetAccumulatedRenderTransform();
	const FSlateBrush* White = FCoreStyle::Get().GetBrush(TEXT("GenericWhiteBox"));
	FSlateRenderer* Renderer = FSlateApplication::Get().GetRenderer();
	const FSlateResourceHandle WhiteHandle = Renderer->GetResourceHandle(*White);

	OutDrawElements.PushClip(FSlateClippingZone(AllottedGeometry));

	// 下地
	FSlateDrawElement::MakeBox(OutDrawElements, LayerId, AllottedGeometry.ToPaintGeometry(), White, ESlateDrawEffect::None, BigMapBackColor);

	// 地図 (見えている範囲だけを切り出して貼る。地図の外は下地のまま)
	TArray<FSlateVertex> Verts;
	TArray<SlateIndex> Indices;
	const FVector2D ViewMin = LocalToWorld(FVector2f::ZeroVector, Size);
	const FVector2D ViewMax = LocalToWorld(Size, Size);
	const FVector2D DrawMin(FMath::Max(ViewMin.X, MapMin.X), FMath::Max(ViewMin.Y, MapMin.Y));
	const FVector2D DrawMax(FMath::Min(ViewMax.X, MapMax.X), FMath::Min(ViewMax.Y, MapMax.Y));
	const FVector2D MapSize = MapMax - MapMin;
	if (DrawMax.X > DrawMin.X && DrawMax.Y > DrawMin.Y)
	{
		const FVector2D Corners[] = {DrawMin, FVector2D(DrawMax.X, DrawMin.Y), DrawMax, FVector2D(DrawMin.X, DrawMax.Y)};
		const FColor Tint = bHasMap ? FColor::White : FColor(40, 60, 45, 230);
		for (const FVector2D& Corner : Corners)
		{
			Verts.Add(FSlateVertex::Make<ESlateVertexRounding::Disabled>(Transform, WorldToLocal(Corner, Size),
			                                                               FVector2f((Corner - MapMin) / MapSize), Tint));
		}
		Indices.Append({0, 1, 2, 0, 2, 3});
		FSlateDrawElement::MakeCustomVerts(OutDrawElements, LayerId + 1, bHasMap ? Renderer->GetResourceHandle(MapBrush) : WhiteHandle,
		                                   Verts, Indices, nullptr, 0, 0);
		Verts.Reset();
		Indices.Reset();
	}

	// 地図の縁
	{
		const FVector2f A = WorldToLocal(MapMin, Size);
		const FVector2f C = WorldToLocal(MapMax, Size);
		const FVector2f B(C.X, A.Y);
		const FVector2f D(A.X, C.Y);
		BigMapLine(Verts, Indices, Transform, A, B, 2.f, BigMapFrameColor);
		BigMapLine(Verts, Indices, Transform, B, C, 2.f, BigMapFrameColor);
		BigMapLine(Verts, Indices, Transform, C, D, 2.f, BigMapFrameColor);
		BigMapLine(Verts, Indices, Transform, D, A, 2.f, BigMapFrameColor);
	}

	// 行き先
	const int32 HoverPoint = HoverLocal.IsSet() && !bDragged ? FindPoint(HoverLocal.GetValue(), Size) : INDEX_NONE;
	static const FVector2f Diamond[] = {{0.f, -1.f}, {1.f, 0.f}, {0.f, 1.f}, {-1.f, 0.f}};
	for (int32 i = 0; i < Points.Num(); ++i)
	{
		const FVector2f P = WorldToLocal(Points[i].Location, Size);
		const float S = i == HoverPoint ? 1.5f : 1.f;
		BigMapPolygon(Verts, Indices, Transform, P, Diamond, 10.f * S, BigMapOutlineColor);
		BigMapPolygon(Verts, Indices, Transform, P, Diamond, 7.5f * S, i == HoverPoint ? BigMapPointHoverColor : BigMapPointColor);
	}

	// 止めてあるバイク
	const APawn* Pawn = Player.Get();
	if (const AActor* Parked = ParkedBike.Get(); Parked && Parked != Pawn)
	{
		static const FVector2f Square[] = {{-1.f, -1.f}, {1.f, -1.f}, {1.f, 1.f}, {-1.f, 1.f}};
		const FVector2f P = WorldToLocal(FVector2D(Parked->GetActorLocation()), Size);
		BigMapPolygon(Verts, Indices, Transform, P, Square, 8.f, BigMapOutlineColor);
		BigMapPolygon(Verts, Indices, Transform, P, Square, 6.f, BigMapParkedColor);
	}

	// プレイヤー (進む向きを指す矢印。画面の右が UE の +X、下が +Y)
	if (Pawn)
	{
		const float Yaw = FMath::DegreesToRadians(Pawn->GetActorRotation().Yaw);
		const FVector2f Forward(FMath::Cos(Yaw), FMath::Sin(Yaw));
		const FVector2f Right(-Forward.Y, Forward.X);
		static const FVector2f Arrow[] = {{0.f, -1.f}, {0.7f, 0.8f}, {0.f, 0.4f}, {-0.7f, 0.8f}};
		const FVector2f P = WorldToLocal(FVector2D(Pawn->GetActorLocation()), Size);
		// Arrow の -Y が前
		BigMapPolygon(Verts, Indices, Transform, P, Arrow, 17.f, BigMapOutlineColor, Right, -Forward);
		BigMapPolygon(Verts, Indices, Transform, P, Arrow, 13.f, BigMapPlayerColor, Right, -Forward);
	}

	// カーソルの所の十字 (行き先の上でないとき)
	if (HoverLocal.IsSet() && HoverPoint == INDEX_NONE && !bDragged)
	{
		const FVector2f C = HoverLocal.GetValue();
		BigMapLine(Verts, Indices, Transform, C - FVector2f(12.f, 0.f), C - FVector2f(4.f, 0.f), 2.f, BigMapCursorColor);
		BigMapLine(Verts, Indices, Transform, C + FVector2f(4.f, 0.f), C + FVector2f(12.f, 0.f), 2.f, BigMapCursorColor);
		BigMapLine(Verts, Indices, Transform, C - FVector2f(0.f, 12.f), C - FVector2f(0.f, 4.f), 2.f, BigMapCursorColor);
		BigMapLine(Verts, Indices, Transform, C + FVector2f(0.f, 4.f), C + FVector2f(0.f, 12.f), 2.f, BigMapCursorColor);
	}

	// 縮尺 (左下)。画面で 120px 前後になるきりのよい長さ
	const double CmPx = CmPerPx(Size);
	const double TargetM = 120.0 * CmPx / 100.0;
	const double Pow10 = FMath::Pow(10.0, FMath::FloorToDouble(FMath::LogX(10.0, FMath::Max(TargetM, 1.0))));
	double BarM = Pow10;
	for (const double Step : {2.0, 5.0, 10.0})
	{
		if (Pow10 * Step <= TargetM)
		{
			BarM = Pow10 * Step;
		}
	}
	const float BarPx = static_cast<float>(BarM * 100.0 / CmPx);
	const FVector2f BarLeft(24.f, Size.Y - 28.f);
	BigMapLine(Verts, Indices, Transform, BarLeft, BarLeft + FVector2f(BarPx, 0.f), 4.f, BigMapFrameColor);

	// 北の矢印 (右上)。升目を回していれば UE の (sin, -cos) が北
	const double GridRot = FMath::DegreesToRadians(static_cast<double>(GridRotationDeg));
	const FVector2f North(static_cast<float>(FMath::Sin(GridRot)), static_cast<float>(-FMath::Cos(GridRot)));
	const FVector2f NorthCenter(Size.X - 40.f, 56.f);
	static const FVector2f NorthArrow[] = {{0.f, -1.f}, {0.5f, 0.6f}, {0.f, 0.3f}, {-0.5f, 0.6f}};
	BigMapPolygon(Verts, Indices, Transform, NorthCenter, NorthArrow, 16.f, BigMapFrameColor, FVector2f(-North.Y, North.X), -North);

	FSlateDrawElement::MakeCustomVerts(OutDrawElements, LayerId + 2, WhiteHandle, Verts, Indices, nullptr, 0, 0);

	// 文字
	const int32 TextLayer = LayerId + 3;
	const FSlateFontInfo LabelFont = FCoreStyle::GetDefaultFontStyle("Bold", 13);
	for (int32 i = 0; i < Points.Num(); ++i)
	{
		const FVector2f P = WorldToLocal(Points[i].Location, Size);
		BigMapText(OutDrawElements, TextLayer, AllottedGeometry, Points[i].Label, LabelFont, P + FVector2f(13.f, -10.f),
		           i == HoverPoint ? FLinearColor(1.f, 0.96f, 0.55f) : FLinearColor::White);
	}
	const FSlateFontInfo SmallFont = FCoreStyle::GetDefaultFontStyle("Regular", 12);
	BigMapText(OutDrawElements, TextLayer, AllottedGeometry,
	           BarM >= 1000.0 ? FString::Printf(TEXT("%g km"), BarM / 1000.0) : FString::Printf(TEXT("%g m"), BarM),
	           SmallFont, BarLeft + FVector2f(0.f, -22.f), FLinearColor::White);
	const FSlateFontInfo NorthFont = FCoreStyle::GetDefaultFontStyle("Bold", 14);
	const FVector2f NSize = BigMapMeasure(TEXT("N"), NorthFont);
	BigMapText(OutDrawElements, TextLayer, AllottedGeometry, TEXT("N"), NorthFont, NorthCenter + North * 30.f - NSize * 0.5f, FLinearColor::White);

	if (HoverLocal.IsSet() && !bDragged)
	{
		const FString Hint = HoverPoint != INDEX_NONE ? Points[HoverPoint].Label + TEXT(" へ移動 (クリック)") : FString(TEXT("ここへ移動 (クリック)"));
		BigMapText(OutDrawElements, TextLayer, AllottedGeometry, Hint, SmallFont, HoverLocal.GetValue() + FVector2f(16.f, 14.f),
		           FLinearColor(0.9f, 0.9f, 0.9f));
	}

	if (!Message.IsEmpty() && FPlatformTime::Seconds() < MessageUntil)
	{
		const FSlateFontInfo MessageFont = FCoreStyle::GetDefaultFontStyle("Bold", 18);
		const FVector2f MSize = BigMapMeasure(Message, MessageFont);
		BigMapText(OutDrawElements, TextLayer, AllottedGeometry, Message, MessageFont, FVector2f((Size.X - MSize.X) * 0.5f, 20.f),
		           FLinearColor(1.f, 0.55f, 0.35f));
	}

	OutDrawElements.PopClip();
	return TextLayer + 1;
}
