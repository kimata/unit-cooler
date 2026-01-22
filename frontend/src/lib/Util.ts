import dayjs from "dayjs";

export const valueText = (value: number | null, digits = 1) => {
    if (value == null) {
        return "?";
    } else {
        return value.toFixed(digits);
    }
};

export const dateText = (date: dayjs.Dayjs | null) => {
    if (date == null) {
        return "?";
    } else {
        return date.format("M/D HH:mm");
    }
};
