#pragma once

#include "CoreMinimal.h"
#include "Styling/SlateBrush.h"
#include "Widgets/SLeafWidget.h"

class APawn;
class UTexture2D;

/**
 * 画面の隅に出す丸いミニマップ。プレイヤー (バイクか歩いている人) の向きが常に上になるよう地図を回す。
 * 地図は tools/terrain/build_minimap.py が作った上から見た画像 (北が上、UE の +X が右、+Y が下)。
 * 速度が上がるほど広い範囲を映す。ファストトラベルの行き先は点で、歩いているときは止めてあるバイクも印で出る。
 */
class SFDMinimap : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SFDMinimap)
		: _MapTexture(nullptr)
		, _MapMin(FVector2D::ZeroVector)
		, _MapMax(FVector2D::ZeroVector)
		, _Diameter(260.f)
		, _RadiusSlowM(250.f)
		, _RadiusFastM(600.f)
		, _GridRotationDeg(0.f)
	{}
		/** 中心に置くプレイヤー (バイクか歩いている人) */
		SLATE_ARGUMENT(TWeakObjectPtr<const APawn>, Player)
		/** 降りて止めてあるバイク。歩いているときに印で出す */
		SLATE_ARGUMENT(TWeakObjectPtr<const AActor>, ParkedBike)
		/** 地図の画像。無いときは無地の円にバイクと行き先だけを出す */
		SLATE_ARGUMENT(UTexture2D*, MapTexture)
		/** 地図の画像の左上 (北西) と右下 (南東) の UE 座標 (cm) */
		SLATE_ARGUMENT(FVector2D, MapMin)
		SLATE_ARGUMENT(FVector2D, MapMax)
		/** 点で出す場所 (UE 座標 cm) */
		SLATE_ARGUMENT(TArray<FVector2D>, Markers)
		/** 直径 (Slate の単位) */
		SLATE_ARGUMENT(float, Diameter)
		/** 止まっているときと速いとき (60km/h 以上) に映す半径 (m) */
		SLATE_ARGUMENT(float, RadiusSlowM)
		SLATE_ARGUMENT(float, RadiusFastM)
		/** コースの升目の回転 (度、AFDCourseInfo)。N の印を真北へ向ける */
		SLATE_ARGUMENT(float, GridRotationDeg)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect,
	                      FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle,
	                      bool bParentEnabled) const override;

private:
	TWeakObjectPtr<const APawn> Player;
	TWeakObjectPtr<const AActor> ParkedBike;
	FSlateBrush MapBrush;
	bool bHasMap = false;
	FVector2D MapMin = FVector2D::ZeroVector;
	FVector2D MapMax = FVector2D::ZeroVector;
	float GridRotationDeg = 0.f;
	TArray<FVector2D> Markers;
	float Diameter = 260.f;
	float RadiusSlowM = 250.f;
	float RadiusFastM = 600.f;

	/** 今映している半径 (m)。速度に合わせてなめらかに変える */
	mutable float RadiusM = 0.f;
};
