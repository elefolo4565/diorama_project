#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "FDWaterRefresh.generated.h"

/**
 * 海 (WaterZone) に、読み込みのあとで地形を読み直させる。
 * 一周コースのレベルを開いた直後は、Ocean が WaterZone に登録されないまま水の範囲 (Water Info) が描かれ、
 * タイルの所の海が描かれず海底の砂が見えたままになる。
 * これを置いておくと、エディタで開いた時もプレイ開始時も、少し待ってから何度か描き直させる。
 * tools/ue/setup_project.py が一周コースのレベルに置く。
 */
UCLASS()
class FUKUOKADRIVE_API AFDWaterRefresh : public AActor
{
	GENERATED_BODY()

public:
	AFDWaterRefresh();

	/** 描き直させる時刻 (読み込んでからの秒数) */
	UPROPERTY(EditAnywhere, Category = "Water")
	TArray<float> RefreshTimes = {1.0f, 3.0f, 8.0f, 20.0f};

	virtual void Tick(float DeltaSeconds) override;
	virtual bool ShouldTickIfViewportsOnly() const override { return true; }

protected:
	virtual void PostLoad() override;
	virtual void BeginPlay() override;

private:
	void Restart();
	void RefreshWaterZones() const;

	double StartTime = -1.0;
	int32 NextRefresh = 0;
};
